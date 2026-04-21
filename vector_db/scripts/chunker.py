"""
scripts/chunker.py — Splits long document text into overlapping chunks for embedding.
"""


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """
    Split text into chunks of ~chunk_size characters with overlap.
    Tries to split on sentence/paragraph boundaries where possible.
    """
    if not text or not text.strip():
        return []

    text = text.strip()

    # If short enough, return as-is
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end >= len(text):
            chunks.append(text[start:].strip())
            break

        # Try to find a good break point (newline or sentence end)
        best_break = end
        for sep in ["\n\n", "\n", ". ", "! ", "? ", " "]:
            idx = text.rfind(sep, start + chunk_size // 2, end)
            if idx != -1:
                best_break = idx + len(sep)
                break

        chunk = text[start:best_break].strip()
        if chunk:
            chunks.append(chunk)

        start = best_break - overlap
        if start < 0:
            start = 0

    return [c for c in chunks if len(c.strip()) > 20]


def chunk_documents(docs: list[dict], chunk_size: int = 800, overlap: int = 100) -> list[dict]:
    """
    Takes a list of {text, source, metadata} dicts,
    splits each into chunks, returns flat list with chunk index in metadata.
    """
    all_chunks = []

    for doc in docs:
        text = doc.get("text", "")
        source = doc.get("source", "")
        meta = doc.get("metadata", {})

        chunks = chunk_text(text, chunk_size, overlap)

        for i, chunk in enumerate(chunks):
            all_chunks.append({
                "text": chunk,
                "source": source,
                "metadata": {
                    **meta,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                }
            })

    return all_chunks