"""
query_kb.py — Search your vector knowledge base from the command line.

Usage:
    python query_kb.py "what is the voltage range of the rk3588?"
    python query_kb.py "solar inverter specs" --top 5
    python query_kb.py "esp32 pinout" --source datasheet
    python query_kb.py "NVMe boot support" --category my_products
"""

import os
import sys
import argparse
from pathlib import Path
import yaml

# ── Load config ───────────────────────────────────────────────

CONFIG_PATH = os.path.join(os.getcwd(), "config.yaml")

def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"config.yaml not found in {os.getcwd()}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def search(query: str, top_k: int = 5, source_filter: str = None, category: str = None):
    config = load_config()
    db_cfg = config.get("vector_db", {})
    emb_cfg = config.get("embedding", {})
    db_path = os.path.join(os.getcwd(), db_cfg.get("path", "db"))
    collection_name = db_cfg.get("collection", "knowledge")
    model_name = emb_cfg.get("model", "all-MiniLM-L6-v2")

    # Load DB
    import chromadb
    client = chromadb.PersistentClient(path=db_path)
    collection = client.get_collection(collection_name)

    # Load embedder
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_name)

    # Embed query
    query_embedding = model.encode([query]).tolist()

    # Build filter
    where = None
    if source_filter and category:
        where = {"$and": [{"source": {"$contains": source_filter}}, {"category": category}]}
    elif category:
        where = {"category": category}
    elif source_filter:
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
        category_meta = meta.get("category", "?")
        type_meta = meta.get("type", "?")

        print(f"\n[{i+1}] Score: {score:.3f}  |  {source}  |  Category: {category_meta}  |  Type: {type_meta}")
        print("-" * 60)
        # Print first 400 chars of chunk
        preview = doc[:400].replace("\n", " ")
        print(f"{preview}{'...' if len(doc) > 400 else ''}")

    return docs, metas


def main():
    parser = argparse.ArgumentParser(description="Search your vector knowledge base")
    parser.add_argument("query", type=str, help="Your search query")
    parser.add_argument("--top",     type=int, default=5, help="Number of results (default: 5)")
    parser.add_argument("--source",  type=str, default=None, help="Filter by source filename substring")
    parser.add_argument("--category", type=str, default=None,
                        choices=["my_products", "competitors", "watchlist"],
                        help="Filter by knowledge base category")
    args = parser.parse_args()

    search(args.query, top_k=args.top, source_filter=args.source, category=args.category)


if __name__ == "__main__":
    main()