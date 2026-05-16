"""
scripts/store.py — Save article drafts to disk.

Saves each article as:
  drafts/YYYY-MM-DD_keyword-slug.md   ← the actual markdown draft
  output/latest_batch.json            ← metadata for all articles in this run
  output/YYYY-MM-DD_HH-MM_batch.json  ← timestamped batch archive
"""

import json
import re
from datetime import datetime
from pathlib import Path


def slugify(text: str) -> str:
    """Convert text to URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text[:60]  # cap at 60 chars


def save_draft(
    content: str,
    context: dict,
    result: dict,
    output_dir: Path,
    drafts_dir: Path,
    date_str: str,
) -> dict:
    """
    Save a single article draft and return its metadata dict.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    drafts_dir.mkdir(parents=True, exist_ok=True)

    keyword = context.get("keyword", "article")
    slug    = slugify(keyword)
    fname   = f"{date_str}_{slug}.md"
    fpath   = drafts_dir / fname

    # Write the markdown draft
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(content)

    metadata = {
        "filename":          fname,
        "filepath":          str(fpath),
        "keyword":           keyword,
        "intent":            context.get("intent", ""),
        "cluster":           context.get("cluster", ""),
        "seo_score":         context.get("seo_score", 0),
        "title":             context.get("title", ""),
        "pain_addressed":    context.get("pain_point", {}).get("label", ""),
        "use_case":          context.get("use_case", {}).get("case", ""),
        "products_used":     [p.get("name", "") for p in context.get("products", [])],
        "word_count":        result.get("word_count", 0),
        "has_frontmatter":   result.get("has_frontmatter", False),
        "has_placeholders":  result.get("has_placeholders", False),
        "quality_flags":     result.get("quality_flags", []),
        "tokens_used":       result.get("tokens_used", 0),
        "status":            "draft",
        "generated_at":      datetime.now().isoformat(),
    }

    return metadata


def save_batch(
    articles: list[dict],
    output_dir: Path,
    run_date: str,
) -> str:
    """
    Save the full batch metadata (all articles in this run).
    Returns path to timestamped batch file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    run_label = datetime.now().strftime("%Y-%m-%d_%H-%M")

    batch = {
        "run_date":     run_date,
        "article_count": len(articles),
        "total_words":  sum(a.get("word_count", 0) for a in articles),
        "total_tokens": sum(a.get("tokens_used", 0) for a in articles),
        "articles":     articles,
    }

    # Timestamped archive
    archive_path = output_dir / f"{run_label}_batch.json"
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(batch, f, indent=2, ensure_ascii=False)

    # Always-latest copy
    latest_path = output_dir / "latest_batch.json"
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(batch, f, indent=2, ensure_ascii=False)

    print(f"  [OK] Batch JSON -> {archive_path}")
    print(f"  [OK] Latest     -> {latest_path}")

    return str(archive_path)


def print_draft_preview(content: str, metadata: dict):
    """Print a clean preview of the generated article to the console."""
    title       = metadata.get("title", "")
    word_count  = metadata.get("word_count", 0)
    flags       = metadata.get("quality_flags", [])
    keyword     = metadata.get("keyword", "")
    fname       = metadata.get("filename", "")

    print(f"\n  {'-'*52}")
    print(f"  [FILE] {fname}")
    print(f"  Title   : {title}")
    print(f"  Keyword : {keyword}")
    print(f"  Words   : {word_count}")

    if flags:
        print(f"  [!] Quality flags:")
        for flag in flags:
            print(f"     - {flag}")
    else:
        print(f"  [OK] Quality: no issues")

    # Show first 200 chars of body (after front matter)
    body = content
    if body.startswith("---"):
        end = body.find("---", 3)
        if end != -1:
            body = body[end + 3:].strip()
    preview = body[:220].replace("\n", " ").strip()
    print(f"\n  Preview: {preview}...")
    print(f"  {'-'*52}")
