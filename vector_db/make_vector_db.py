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


def safe_print(msg: str):
    """Print safely on Windows cp1252 terminals by replacing unencodable chars."""
    try:
        print(msg)
    except UnicodeEncodeError:
        safe = msg.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
               sys.stdout.encoding or "utf-8", errors="replace")
        print(safe)

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

def _get_category(source_path: str) -> str:
    """Extract category from path: my_products / competitors / watchlist"""
    path = source_path.replace("\\", "/").lower()
    for cat in ("my_products", "competitors", "watchlist"):
        if f"/{cat}/" in path or path.endswith(f"/{cat}"):
            return cat
    return "watchlist"  # default fallback instead of "general"


def _get_collection_name(category: str, collections_map: dict) -> str:
    """Map category to collection name."""
    return collections_map.get(category, collections_map.get("watchlist", "knowledge"))


def _chunk_content_hash(text: str) -> str:
    """SHA-256 hash of chunk text for deduplication."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


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
    legacy_collection_name = db_cfg.get("collection", "knowledge")
    collections_map = db_cfg.get("collections", {
        "my_products": "knowledge_my_products",
        "competitors": "knowledge_competitors",
        "watchlist": "knowledge_watchlist",
    })
    rebuild = rebuild or db_cfg.get("rebuild", False)

    chunk_size = emb_cfg.get("chunk_size", 800)
    chunk_overlap = emb_cfg.get("chunk_overlap", 100)
    model_name = emb_cfg.get("model", "all-MiniLM-L6-v2")

    log_path = os.path.join(os.getcwd(), log_cfg.get("log_file", "db/build_log.json"))
    verbose = log_cfg.get("verbose", True)

    # ── Imports ───────────────────────────────────────────────
    safe_print("\nLoading dependencies...")
    try:
        import chromadb
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        safe_print(f"❌ Missing dependency: {e}")
        safe_print("   Run: pip install -r requirements.txt")
        sys.exit(1)

    from scripts.loaders import load_folder, load_file, load_url
    from scripts.chunker import chunk_documents

    # ── Embedding model ───────────────────────────────────────
    safe_print(f"Loading embedding model: {model_name}")
    model = SentenceTransformer(model_name)

    # ── ChromaDB ──────────────────────────────────────────────
    os.makedirs(db_path, exist_ok=True)
    client = chromadb.PersistentClient(path=db_path)

    if rebuild:
        for cname in list(collections_map.values()) + [legacy_collection_name]:
            safe_print(f"Rebuilding — deleting collection '{cname}'...")
            try:
                client.delete_collection(cname)
            except Exception:
                pass

    # Helper to get or create a collection
    def get_collection(name: str):
        return client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})

    # Pre-fetch all collections we'll need
    collections = {}
    for cat, cname in collections_map.items():
        collections[cname] = get_collection(cname)

    build_log = BuildLog(log_path)
    if rebuild:
        build_log.data["indexed"] = {}

    # ── Collect all sources ───────────────────────────────────
    safe_print("\nScanning knowledge base...")
    all_docs = []
    skipped = 0
    sources_processed = []

    # Folders
    for folder in kb_cfg.get("folders", []):
        folder_abs = os.path.join(os.getcwd(), folder)
        if not os.path.exists(folder_abs):
            safe_print(f"  ⚠ Folder not found: {folder_abs}")
            continue

        safe_print(f"\n  Folder: {folder}")
        from pathlib import Path as P
        supported = {".pdf", ".xlsx", ".xls", ".docx", ".doc", ".txt", ".md", ".csv"}
        for fpath in sorted(P(folder_abs).rglob("*")):
            if fpath.is_file() and fpath.suffix.lower() in supported:
                fhash = file_hash(str(fpath))
                if not rebuild and build_log.is_indexed(str(fpath), fhash):
                    safe_print(f"    Unchanged: {fpath.name}")
                    skipped += 1
                    continue
                safe_print(f"    Loading: {fpath.name}")
                docs = load_file(str(fpath))
                for d in docs:
                    d["_hash"] = fhash
                all_docs.extend(docs)
                sources_processed.append(str(fpath))

    # Explicit files
    for fpath in kb_cfg.get("files", []) or []:
        if not os.path.exists(fpath):
            safe_print(f"  ⚠ File not found: {fpath}")
            continue
        fhash = file_hash(fpath)
        if not rebuild and build_log.is_indexed(fpath, fhash):
            safe_print(f"    Unchanged: {os.path.basename(fpath)}")
            skipped += 1
            continue
        safe_print(f"    Loading: {fpath}")
        docs = load_file(fpath)
        for d in docs:
            d["_hash"] = fhash
        all_docs.extend(docs)
        sources_processed.append(fpath)

    # URLs
    urls = kb_cfg.get("urls", []) or []
    if urls:
        safe_print(f"\n  Fetching {len(urls)} URLs...")
    for url in urls:
        if not rebuild and build_log.is_indexed(url):
            safe_print(f"    Already indexed: {url}")
            skipped += 1
            continue
        safe_print(f"    {url}")
        docs = load_url(url)
        all_docs.extend(docs)
        if docs:
            sources_processed.append(url)

    if not all_docs:
        safe_print("\nNothing new to index.")
        stats()
        return

    # ── Chunk ─────────────────────────────────────────────────
    safe_print(f"\nChunking {len(all_docs)} documents (size={chunk_size}, overlap={chunk_overlap})...")
    chunks = chunk_documents(all_docs, chunk_size, chunk_overlap)
    safe_print(f"   → {len(chunks)} total chunks")

    # ── Embed & store ─────────────────────────────────────────
    safe_print(f"\nEmbedding and storing in ChromaDB...")

    texts = [c["text"] for c in chunks]
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=32).tolist()

    # Group chunks by target collection
    collection_batches: dict[str, dict] = {}
    for cname in collections.keys():
        collection_batches[cname] = {"ids": [], "metas": [], "docs": [], "embeds": []}

    seen_hashes_per_collection: dict[str, set] = {cname: set() for cname in collections.keys()}

    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        category = _get_category(chunk["source"])
        cname = _get_collection_name(category, collections_map)
        if cname not in collections:
            cname = list(collections.keys())[0]  # fallback

        # Compute content hash for deduplication
        content_hash = _chunk_content_hash(chunk["text"])

        # Check if we've seen this exact content in this batch
        if content_hash in seen_hashes_per_collection[cname]:
            continue
        seen_hashes_per_collection[cname].add(content_hash)

        # Check if this content hash already exists in DB (for incremental builds)
        if not rebuild:
            try:
                existing = collections[cname].get(ids=[content_hash])
                if existing and existing.get("ids"):
                    # Duplicate found — update published_date if newer, then skip
                    existing_meta = existing.get("metadatas", [{}])[0]
                    existing_date = existing_meta.get("published_date", "")
                    new_date = str(chunk["metadata"].get("published_date", ""))
                    if new_date and (not existing_date or new_date > existing_date):
                        collections[cname].update(
                            ids=[content_hash],
                            metadatas=[{**existing_meta, "published_date": new_date}]
                        )
                    continue
            except Exception:
                pass  # ID doesn't exist, proceed

        # ChromaDB metadata must be flat strings/ints/floats
        flat_meta = {
            "source": str(chunk["source"]),
            "type": str(chunk["metadata"].get("type", "unknown")),
            "chunk_index": int(chunk["metadata"].get("chunk_index", 0)),
            "category": category,
            "content_hash": content_hash,
        }
        # Add published_date if available
        pub_date = chunk["metadata"].get("published_date")
        if pub_date:
            flat_meta["published_date"] = str(pub_date)

        # Add optional metadata fields
        for key in ["page", "sheet", "file", "url"]:
            if key in chunk["metadata"]:
                flat_meta[key] = str(chunk["metadata"][key])

        collection_batches[cname]["ids"].append(content_hash)
        collection_batches[cname]["metas"].append(flat_meta)
        collection_batches[cname]["docs"].append(chunk["text"])
        collection_batches[cname]["embeds"].append(emb)

    # Upsert per collection in batches of 500
    total_stored = 0
    batch_size = 500
    for cname, batch in collection_batches.items():
        total = len(batch["ids"])
        if total == 0:
            continue
        safe_print(f"   Collection '{cname}': {total} chunks...")
        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            collections[cname].upsert(
                ids=batch["ids"][start:end],
                embeddings=batch["embeds"][start:end],
                documents=batch["docs"][start:end],
                metadatas=batch["metas"][start:end],
            )
        total_stored += total

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
        "chunks_added": total_stored,
        "rebuild": rebuild,
    })

    safe_print(f"\nDone!")
    safe_print(f"   Sources indexed: {len(sources_processed)}")
    safe_print(f"   Sources skipped (unchanged): {skipped}")
    safe_print(f"   Chunks stored: {total_stored}")
    safe_print(f"   DB path: {db_path}")


# ── Stats ─────────────────────────────────────────────────────

def stats():
    config = load_config()
    db_cfg = config.get("vector_db", {})
    db_path = os.path.join(os.getcwd(), db_cfg.get("path", "db"))
    legacy_collection = db_cfg.get("collection", "knowledge")
    collections_map = db_cfg.get("collections", {
        "my_products": "knowledge_my_products",
        "competitors": "knowledge_competitors",
        "watchlist": "knowledge_watchlist",
    })

    try:
        import chromadb
        client = chromadb.PersistentClient(path=db_path)
        safe_print(f"\nVector DB Stats")
        safe_print(f"   DB path: {db_path}")
        for cat, cname in collections_map.items():
            try:
                col = client.get_collection(cname)
                count = col.count()
                safe_print(f"   Collection '{cname}' ({cat}): {count} chunks")
            except Exception:
                safe_print(f"   Collection '{cname}' ({cat}): not found")
        # Legacy collection
        try:
            col = client.get_collection(legacy_collection)
            count = col.count()
            safe_print(f"   Collection '{legacy_collection}' (legacy): {count} chunks")
        except Exception:
            pass
    except Exception as e:
        safe_print(f"  ⚠ Could not read DB: {e}")

    log_path = os.path.join(os.getcwd(), config.get("logging", {}).get("log_file", "db/build_log.json"))
    if os.path.exists(log_path):
        with open(log_path) as f:
            log = json.load(f)
        indexed = log.get("indexed", {})
        safe_print(f"   Sources    : {len(indexed)}")
        if indexed:
            safe_print(f"\n   Indexed sources:")
            for src, info in indexed.items():
                safe_print(f"     - {os.path.basename(src)} — {info['chunks']} chunks ({info['indexed_at'][:10]})")


# ── Query test ────────────────────────────────────────────────

def query(q: str, n: int = 5, collection_name: str = None):
    config = load_config()
    db_cfg = config.get("vector_db", {})
    emb_cfg = config.get("embedding", {})
    db_path = os.path.join(os.getcwd(), db_cfg.get("path", "db"))
    collections_map = db_cfg.get("collections", {
        "my_products": "knowledge_my_products",
        "competitors": "knowledge_competitors",
        "watchlist": "knowledge_watchlist",
    })
    default_collection = db_cfg.get("collection", "knowledge")
    target = collection_name or default_collection
    model_name = emb_cfg.get("model", "all-MiniLM-L6-v2")

    import chromadb
    from sentence_transformers import SentenceTransformer

    client = chromadb.PersistentClient(path=db_path)
    model = SentenceTransformer(model_name)

    safe_print(f"\nQuery: '{q}'")
    embedding = model.encode([q]).tolist()

    def query_one(cname: str):
        try:
            col = client.get_collection(cname)
            res = col.query(query_embeddings=embedding, n_results=n)
            docs = res.get("documents", [[]])[0]
            metas = res.get("metadatas", [[]])[0]
            dists = res.get("distances", [[]])[0]
            out = []
            for doc, meta, dist in zip(docs, metas, dists):
                score = round(1 - dist, 4)
                out.append({"score": score, "doc": doc, "meta": meta, "collection": cname})
            return out
        except Exception as e:
            safe_print(f"  ⚠ Collection '{cname}' query failed: {e}")
            return []

    if target == "all":
        all_results = []
        for cname in list(collections_map.values()) + [default_collection]:
            all_results.extend(query_one(cname))
        all_results.sort(key=lambda x: x["score"], reverse=True)
        results = all_results[:n]
    else:
        results = query_one(target)

    safe_print(f"\nTop {len(results)} results:\n")
    for i, r in enumerate(results):
        score = r["score"]
        meta = r["meta"]
        doc = r["doc"]
        cname = r.get("collection", target)
        pub_date = meta.get("published_date", "")
        date_str = f" | Date: {pub_date}" if pub_date else ""
        safe_print(f"  [{i+1}] Score: {score} | Collection: {cname} | Source: {meta.get('source', '?')} | Type: {meta.get('type','?')}{date_str}")
        safe_print(f"       {doc[:200].strip()}...")
        safe_print()


# ── Entry point ───────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build or query a ChromaDB vector database")
    parser.add_argument("--rebuild", action="store_true", help="Wipe and rebuild the entire DB")
    parser.add_argument("--stats",   action="store_true", help="Show DB stats and exit")
    parser.add_argument("--query",   type=str, default=None, help="Test a semantic search query")
    parser.add_argument("--top",     type=int, default=5, help="Number of results to return (default: 5)")
    parser.add_argument("--category", type=str, default=None,
                    choices=["my_products", "competitors", "watchlist"],
                    help="Filter by knowledge base category")
    parser.add_argument("--collection", type=str, default=None,
                    help="Query specific collection name (or 'all' for all collections)")
    args = parser.parse_args()

    if args.stats:
        stats()
    elif args.query:
        target = args.collection
        if args.category and not target:
            cfg = load_config()
            cmap = cfg.get("vector_db", {}).get("collections", {})
            target = cmap.get(args.category)
        query(args.query, args.top, collection_name=target)
    else:
        build(rebuild=args.rebuild)