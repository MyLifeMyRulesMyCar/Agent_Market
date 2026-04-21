"""
query_kb.py — Search your vector knowledge base from the command line.

Usage:
    python query_kb.py "what is the voltage range of the rk3588?"
    python query_kb.py "solar inverter specs" --top 5
    python query_kb.py "esp32 pinout" --source datasheet
"""

import os
import sys
import argparse
from pathlib import Path
import yaml

ROOT = Path(os.getcwd())
CONFIG_PATH = ROOT / "config" / "knowledge_base.yml"
sys.path.insert(0, str(ROOT))


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def search(query: str, top_k: int = 5, source_filter: str = None):
    config = load_config()
    settings = config["settings"]

    # Load DB
    import chromadb
    db_dir = ROOT / settings["db_dir"]
    client = chromadb.PersistentClient(path=str(db_dir))
    collection = client.get_collection(settings.get("collection_name", "knowledge_base"))

    # Load embedder
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(settings.get("embedding_model", "all-MiniLM-L6-v2"))

    # Embed query
    query_embedding = model.encode([query]).tolist()

    # Build filter
    where = None
    if source_filter:
        where = {"source": {"$contains": source_filter}}

    # Query
    results = collection.query(
        query_embeddings=query_embedding,
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    distances = results["distances"][0]

    print(f"\n🔍 Query: \"{query}\"")
    print(f"{'='*60}")

    for i, (doc, meta, dist) in enumerate(zip(docs, metas, distances)):
        score = round(1 - dist, 3)  # cosine distance → similarity
        source = Path(meta.get("source", "?")).name
        page = meta.get("page", "?")
        label = meta.get("label", "")

        print(f"\n[{i+1}] Score: {score:.3f}  |  {source}  (page {page})  [{label}]")
        print("-" * 60)
        # Print first 400 chars of chunk
        preview = doc[:400].replace("\n", " ")
        print(f"{preview}{'...' if len(doc) > 400 else ''}")

    return docs, metas


def main():
    parser = argparse.ArgumentParser(description="Search your vector knowledge base")
    parser.add_argument("query", type=str, help="Your search query")
    parser.add_argument("--top",    type=int, default=5, help="Number of results (default: 5)")
    parser.add_argument("--source", type=str, default=None, help="Filter by source filename substring")
    args = parser.parse_args()

    search(args.query, top_k=args.top, source_filter=args.source)


if __name__ == "__main__":
    main()