"""
make_vector_db.py — Build or update a ChromaDB vector database
from local files (PDF, Excel, Word, TXT, MD, CSV) and web URLs.

Usage:
    python make_vector_db.py                  # incremental update
    python make_vector_db.py --rebuild        # wipe and rebuild from scratch
    python make_vector_db.py --query "esp32"  # test a search after building
    python make_vector_db.py --stats          # show DB stats only

Requirements:
    pip install -r requirements.txt
"""

import os
import sys
import json
import yaml
import hashlib
import argparse
from datetime import datetime
from pathlib import Path

# ── Load config ───────────────────────────────────────────────

CONFIG_PATH = os.path.join(os.getcwd(), "config.yaml")

def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"config.yaml not found in {os.getcwd()}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Hashing for change detection ─────────────────────────────

def file_hash(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def source_id(source: str) -> str:
    """Stable ID for a source (file path or URL)."""
    return hashlib.md5(source.encode()).hexdigest()


# ── Build log (tracks what's already indexed) ─────────────────

class BuildLog:
    def __init__(self, log_path: str):
        self.path = log_path
        self.data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.path):
            with open(self.path) as f:
                return json.load(f)
        return {"indexed": {}, "runs": []}

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent=2)

    def is_indexed(self, source: str, current_hash: str = None) -> bool:
        entry = self.data["indexed"].get(source)
        if not entry:
            return False
        if current_hash and entry.get("hash") != current_hash:
            return False  # file changed
        return True

    def mark_indexed(self, source: str, chunk_count: int, hash_val: str = None):
        self.data["indexed"][source] = {
            "chunks": chunk_count,
            "hash": hash_val,
            "indexed_at": datetime.now().isoformat()
        }

    def record_run(self, stats: dict):
        self.data["runs"].append({
            "timestamp": datetime.now().isoformat(),
            **stats
        })
        self.save()


# ── Main build function ───────────────────────────────────────

def build(rebuild: bool = False):
    config = load_config()
    kb_cfg = config.get("knowledge_base", {})
    emb_cfg = config.get("embedding", {})
    db_cfg = config.get("vector_db", {})
    log_cfg = config.get("logging", {})

    db_path = os.path.join(os.getcwd(), db_cfg.get("path", "db"))
    collection_name = db_cfg.get("collection", "knowledge")
    rebuild = rebuild or db_cfg.get("rebuild", False)

    chunk_size = emb_cfg.get("chunk_size", 800)
    chunk_overlap = emb_cfg.get("chunk_overlap", 100)
    model_name = emb_cfg.get("model", "all-MiniLM-L6-v2")

    log_path = os.path.join(os.getcwd(), log_cfg.get("log_file", "db/build_log.json"))
    verbose = log_cfg.get("verbose", True)

    # ── Imports ───────────────────────────────────────────────
    print("\n🔧 Loading dependencies...")
    try:
        import chromadb
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("   Run: pip install -r requirements.txt")
        sys.exit(1)

    from scripts.loaders import load_folder, load_file, load_url
    from scripts.chunker import chunk_documents

    # ── Embedding model ───────────────────────────────────────
    print(f"🧠 Loading embedding model: {model_name}")
    model = SentenceTransformer(model_name)

    # ── ChromaDB ──────────────────────────────────────────────
    os.makedirs(db_path, exist_ok=True)
    client = chromadb.PersistentClient(path=db_path)

    if rebuild:
        print(f"🗑️  Rebuilding — deleting existing collection '{collection_name}'...")
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}
    )

    build_log = BuildLog(log_path)
    if rebuild:
        build_log.data["indexed"] = {}

    # ── Collect all sources ───────────────────────────────────
    print("\n📂 Scanning knowledge base...")
    all_docs = []
    skipped = 0
    sources_processed = []

    # Folders
    for folder in kb_cfg.get("folders", []):
        folder_abs = os.path.join(os.getcwd(), folder)
        if not os.path.exists(folder_abs):
            print(f"  ⚠ Folder not found: {folder_abs}")
            continue

        print(f"\n  📁 Folder: {folder}")
        from pathlib import Path as P
        supported = {".pdf", ".xlsx", ".xls", ".docx", ".doc", ".txt", ".md", ".csv"}
        for fpath in sorted(P(folder_abs).rglob("*")):
            if fpath.is_file() and fpath.suffix.lower() in supported:
                fhash = file_hash(str(fpath))
                if not rebuild and build_log.is_indexed(str(fpath), fhash):
                    print(f"    ⏭  Unchanged: {fpath.name}")
                    skipped += 1
                    continue
                print(f"    📄 Loading: {fpath.name}")
                docs = load_file(str(fpath))
                for d in docs:
                    d["_hash"] = fhash
                all_docs.extend(docs)
                sources_processed.append(str(fpath))

    # Explicit files
    for fpath in kb_cfg.get("files", []) or []:
        if not os.path.exists(fpath):
            print(f"  ⚠ File not found: {fpath}")
            continue
        fhash = file_hash(fpath)
        if not rebuild and build_log.is_indexed(fpath, fhash):
            print(f"    ⏭  Unchanged: {os.path.basename(fpath)}")
            skipped += 1
            continue
        print(f"    📄 Loading: {fpath}")
        docs = load_file(fpath)
        for d in docs:
            d["_hash"] = fhash
        all_docs.extend(docs)
        sources_processed.append(fpath)

    # URLs
    urls = kb_cfg.get("urls", []) or []
    if urls:
        print(f"\n  🌐 Fetching {len(urls)} URLs...")
    for url in urls:
        if not rebuild and build_log.is_indexed(url):
            print(f"    ⏭  Already indexed: {url}")
            skipped += 1
            continue
        print(f"    🔗 {url}")
        docs = load_url(url)
        all_docs.extend(docs)
        if docs:
            sources_processed.append(url)

    if not all_docs:
        print("\n✅ Nothing new to index.")
        stats()
        return

    # ── Chunk ─────────────────────────────────────────────────
    print(f"\n✂️  Chunking {len(all_docs)} documents (size={chunk_size}, overlap={chunk_overlap})...")
    chunks = chunk_documents(all_docs, chunk_size, chunk_overlap)
    print(f"   → {len(chunks)} total chunks")

    # ── Embed & store ─────────────────────────────────────────
    print(f"\n⚡ Embedding and storing in ChromaDB...")

    texts = [c["text"] for c in chunks]
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=32).tolist()

    # Build IDs and metadata for ChromaDB
    ids, metas, docs_list, embeds_list = [], [], [], []
    seen_ids = set()

    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        # Unique ID: hash of source + chunk index
        raw_id = f"{chunk['source']}::chunk::{chunk['metadata'].get('chunk_index', i)}"
        cid = hashlib.md5(raw_id.encode()).hexdigest()

        if cid in seen_ids:
            continue
        seen_ids.add(cid)

        # ChromaDB metadata must be flat strings/ints/floats
        flat_meta = {
            "source": str(chunk["source"]),
            "type": str(chunk["metadata"].get("type", "unknown")),
            "chunk_index": int(chunk["metadata"].get("chunk_index", 0)),
        }
        # Add optional metadata fields
        for key in ["page", "sheet", "file", "url"]:
            if key in chunk["metadata"]:
                flat_meta[key] = str(chunk["metadata"][key])

        ids.append(cid)
        metas.append(flat_meta)
        docs_list.append(chunk["text"])
        embeds_list.append(emb)

    # Upsert in batches of 500
    batch_size = 500
    total = len(ids)
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        collection.upsert(
            ids=ids[start:end],
            embeddings=embeds_list[start:end],
            documents=docs_list[start:end],
            metadatas=metas[start:end],
        )
        print(f"   Stored {end}/{total} chunks...")

    # ── Update build log ──────────────────────────────────────
    source_chunk_counts = {}
    for chunk in chunks:
        s = chunk["source"]
        source_chunk_counts[s] = source_chunk_counts.get(s, 0) + 1

    for doc in all_docs:
        src = doc["source"]
        h = doc.get("_hash")
        build_log.mark_indexed(src, source_chunk_counts.get(src, 0), h)

    build_log.record_run({
        "sources_added": len(sources_processed),
        "sources_skipped": skipped,
        "chunks_added": total,
        "rebuild": rebuild,
    })

    print(f"\n✅ Done!")
    print(f"   Sources indexed: {len(sources_processed)}")
    print(f"   Sources skipped (unchanged): {skipped}")
    print(f"   Chunks stored: {total}")
    print(f"   DB path: {db_path}")


# ── Stats ─────────────────────────────────────────────────────

def stats():
    config = load_config()
    db_cfg = config.get("vector_db", {})
    db_path = os.path.join(os.getcwd(), db_cfg.get("path", "db"))
    collection_name = db_cfg.get("collection", "knowledge")

    try:
        import chromadb
        client = chromadb.PersistentClient(path=db_path)
        col = client.get_collection(collection_name)
        count = col.count()
        print(f"\n📊 Vector DB Stats")
        print(f"   Collection : {collection_name}")
        print(f"   DB path    : {db_path}")
        print(f"   Chunks     : {count}")
    except Exception as e:
        print(f"  ⚠ Could not read DB: {e}")

    log_path = os.path.join(os.getcwd(), config.get("logging", {}).get("log_file", "db/build_log.json"))
    if os.path.exists(log_path):
        with open(log_path) as f:
            log = json.load(f)
        indexed = log.get("indexed", {})
        print(f"   Sources    : {len(indexed)}")
        if indexed:
            print(f"\n   Indexed sources:")
            for src, info in indexed.items():
                print(f"     • {os.path.basename(src)} — {info['chunks']} chunks ({info['indexed_at'][:10]})")


# ── Query test ────────────────────────────────────────────────

def query(q: str, n: int = 5):
    config = load_config()
    db_cfg = config.get("vector_db", {})
    emb_cfg = config.get("embedding", {})
    db_path = os.path.join(os.getcwd(), db_cfg.get("path", "db"))
    collection_name = db_cfg.get("collection", "knowledge")
    model_name = emb_cfg.get("model", "all-MiniLM-L6-v2")

    import chromadb
    from sentence_transformers import SentenceTransformer

    client = chromadb.PersistentClient(path=db_path)
    col = client.get_collection(collection_name)
    model = SentenceTransformer(model_name)

    print(f"\n🔍 Query: '{q}'")
    embedding = model.encode([q]).tolist()
    results = col.query(query_embeddings=embedding, n_results=n)

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    print(f"\n📋 Top {len(docs)} results:\n")
    for i, (doc, meta, dist) in enumerate(zip(docs, metas, distances)):
        score = round(1 - dist, 3)
        print(f"  [{i+1}] Score: {score} | Source: {meta.get('source', '?')} | Type: {meta.get('type','?')}")
        print(f"       {doc[:200].strip()}...")
        print()


# ── Entry point ───────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build or query a ChromaDB vector database")
    parser.add_argument("--rebuild", action="store_true", help="Wipe and rebuild the entire DB")
    parser.add_argument("--stats",   action="store_true", help="Show DB stats and exit")
    parser.add_argument("--query",   type=str, default=None, help="Test a semantic search query")
    parser.add_argument("--top",     type=int, default=5, help="Number of results to return (default: 5)")
    args = parser.parse_args()

    if args.stats:
        stats()
    elif args.query:
        query(args.query, args.top)
    else:
        build(rebuild=args.rebuild)