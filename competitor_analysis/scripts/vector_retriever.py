"""
scripts/vector_retriever.py — Query the existing Vector DB for competitor info.

The vector_db/ folder lives at the project root (Marketing_agents/vector_db/).
ChromaDB files are stored at Marketing_agents/vector_db/db/.
Config is read from Marketing_agents/vector_db/config.yaml to get the
correct model name and collection name.

The embedding model is loaded ONCE at module level and reused across all
competitor queries — this avoids the repeated BertModel LOAD REPORT warnings
and is significantly faster (model load takes ~1-2s each time).

Now supports:
  - Multi-collection queries (knowledge_my_products, knowledge_competitors, etc.)
  - Freshness + uniqueness re-ranking
  - category_filter wired to the correct collection
"""

import math
from pathlib import Path

# ── Module-level cache: model loaded once, reused for all queries ─────────
_model_cache: dict = {}   # key: model_name → SentenceTransformer instance
_chroma_cache: dict = {}  # key: db_path → chromadb.PersistentClient instance


def _get_model(model_name: str):
    """Load embedding model once and cache it in memory."""
    if model_name not in _model_cache:
        try:
            from sentence_transformers import SentenceTransformer
            import logging
            # Suppress the harmless 'UNEXPECTED key' warnings from transformers
            logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
            logging.getLogger("transformers").setLevel(logging.ERROR)
            print(f"  Loading embedding model: {model_name} (once)...")
            _model_cache[model_name] = SentenceTransformer(model_name)
        except ImportError:
            raise ImportError("sentence-transformers not installed. Run: pip install sentence-transformers")
    return _model_cache[model_name]


def _get_chroma_client(db_path: str):
    """Get or create a ChromaDB client, cached per db_path."""
    if db_path not in _chroma_cache:
        try:
            import chromadb
            _chroma_cache[db_path] = chromadb.PersistentClient(path=db_path)
        except ImportError:
            raise ImportError("chromadb not installed. Run: pip install chromadb")
    return _chroma_cache[db_path]


def _resolve_collection(config: dict, category_filter: str | None) -> str:
    """Map category_filter to collection name using config."""
    db_cfg = config.get("vector_db", {})
    collections_map = db_cfg.get("collections", {
        "my_products": "knowledge_my_products",
        "competitors": "knowledge_competitors",
        "watchlist": "knowledge_watchlist",
    })
    legacy = db_cfg.get("collection", "knowledge")

    if category_filter and category_filter in collections_map:
        return collections_map[category_filter]
    return legacy


def _compute_freshness_weight(published_date: str | None) -> float:
    """Exponential decay with 90-day half-life."""
    if not published_date:
        return 1.0
    try:
        from datetime import datetime
        pub = datetime.strptime(published_date[:10], "%Y-%m-%d")
        days = (datetime.now() - pub).days
        if days < 0:
            return 1.0
        # half-life = 90 days
        return math.exp(-days / 90.0 * math.log(2))
    except Exception:
        return 1.0


def _re_rank_results(results: list[dict]) -> list[dict]:
    """
    Re-rank results by freshness and uniqueness.

    final_score = cosine_similarity × freshness_weight × uniqueness_weight

    where:
      freshness_weight = exp(-days_since_published / 90 * ln(2))
      uniqueness_weight = 1 / (1 + count_of_similar_chunks)

    "Count of similar chunks" = number of chunks in result set with
    cosine similarity > 0.92 to this chunk.
    """
    SIMILARITY_THRESHOLD = 0.92

    # Compute similarity matrix for uniqueness
    n = len(results)
    for i, r in enumerate(results):
        count_similar = 0
        for j, other in enumerate(results):
            if i != j and other["score"] > SIMILARITY_THRESHOLD:
                count_similar += 1
        uniqueness_weight = 1.0 / (1.0 + count_similar)
        freshness_weight = _compute_freshness_weight(r["metadata"].get("published_date"))
        r["final_score"] = r["score"] * freshness_weight * uniqueness_weight
        r["freshness_weight"] = round(freshness_weight, 3)
        r["uniqueness_weight"] = round(uniqueness_weight, 3)

    # Sort by final_score descending
    results.sort(key=lambda x: x["final_score"], reverse=True)
    return results


def query_vector_db(
    project_root: Path,
    query: str,
    top_k: int = 5,
    min_score: float = 0.3,
    category_filter: str = None,
) -> list[dict]:
    """
    Query the ChromaDB knowledge base at project_root/vector_db/db.

    The embedding model is loaded only on the first call and reused
    for all subsequent queries in the same process.

    Returns list of:
      {
        "text":     str,    # chunk text
        "source":   str,    # source file / URL
        "score":    float,  # cosine similarity (0-1)
        "metadata": dict,
        "final_score": float,  # after re-ranking
      }
    """
    db_path     = project_root / "vector_db" / "db"
    config_path = project_root / "vector_db" / "config.yaml"

    if not db_path.exists():
        print(f"  ⚠  Vector DB not found at: {db_path}")
        print(f"      Run: cd vector_db && python make_vector_db.py")
        return []

    try:
        import yaml

        # Read model name and collection from vector_db/config.yaml
        model_name      = "all-MiniLM-L6-v2"
        collection_name = "knowledge"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                vcfg = yaml.safe_load(f)
            model_name      = vcfg.get("embedding", {}).get("model", model_name)
            collection_name = _resolve_collection(vcfg, category_filter)

        # Use cached client + model — no re-loading between competitors
        client = _get_chroma_client(str(db_path))
        model  = _get_model(model_name)

        try:
            collection = client.get_collection(collection_name)
        except Exception:
            # Fall back to legacy collection if new one doesn't exist
            try:
                collection = client.get_collection("knowledge")
                print(f"  ⚠  Collection '{collection_name}' not found, falling back to 'knowledge'")
            except Exception:
                print(f"  ⚠  Collection '{collection_name}' not found in Vector DB")
                print(f"      Run: cd vector_db && python make_vector_db.py")
                return []

        embedding = model.encode([query]).tolist()

        where = {"category": category_filter} if category_filter else None

        # Query more than top_k so re-ranking has enough context
        query_n = max(top_k * 3, 15)
        results = collection.query(
            query_embeddings=embedding,
            n_results=query_n,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        docs      = results.get("documents", [[]])[0]
        metas     = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        output = []
        for doc, meta, dist in zip(docs, metas, distances):
            score = round(1.0 - dist, 4)
            if score < min_score:
                continue
            output.append({
                "text":     doc,
                "source":   meta.get("source", ""),
                "score":    score,
                "metadata": meta,
            })

        # Re-rank by freshness + uniqueness
        output = _re_rank_results(output)

        # Return top_k after re-ranking
        return output[:top_k]

    except ImportError as e:
        print(f"  ⚠  Vector DB dependency missing: {e}")
        print(f"      Run: pip install chromadb sentence-transformers")
        return []
    except Exception as e:
        print(f"  ⚠  Vector DB query failed: {e}")
        return []
