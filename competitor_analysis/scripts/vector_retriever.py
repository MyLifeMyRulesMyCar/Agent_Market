"""
scripts/vector_retriever.py — Query the existing Vector DB for competitor info.

The vector_db/ folder lives at the project root (Marketing_agents/vector_db/).
ChromaDB files are stored at Marketing_agents/vector_db/db/.
Config is read from Marketing_agents/vector_db/config.yaml to get the
correct model name and collection name.

The embedding model is loaded ONCE at module level and reused across all
competitor queries — this avoids the repeated BertModel LOAD REPORT warnings
and is significantly faster (model load takes ~1-2s each time).
"""

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
            collection_name = vcfg.get("vector_db", {}).get("collection", collection_name)

        # Use cached client + model — no re-loading between competitors
        client = _get_chroma_client(str(db_path))
        model  = _get_model(model_name)

        try:
            collection = client.get_collection(collection_name)
        except Exception:
            print(f"  ⚠  Collection '{collection_name}' not found in Vector DB")
            print(f"      Run: cd vector_db && python make_vector_db.py")
            return []

        embedding = model.encode([query]).tolist()

        where = {"category": category_filter} if category_filter else None

        results = collection.query(
            query_embeddings=embedding,
            n_results=top_k,
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

        return output

    except ImportError as e:
        print(f"  ⚠  Vector DB dependency missing: {e}")
        print(f"      Run: pip install chromadb sentence-transformers")
        return []
    except Exception as e:
        print(f"  ⚠  Vector DB query failed: {e}")
        return []