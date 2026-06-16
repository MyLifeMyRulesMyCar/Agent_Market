"""
scripts/writer.py — Call Groq to generate blog article drafts.

One API call per article. Uses llama-3.3-70b-versatile with
a high token limit (3000) to ensure full articles aren't cut off.
Includes basic quality checks on the output.
"""

import os
import re
from pathlib import Path

try:
    from dotenv import load_dotenv
    _here = Path(__file__).parent.parent
    load_dotenv(_here / ".env")
    load_dotenv(_here.parent / ".env")
except ImportError:
    pass


def _get_client():
    try:
        from groq import Groq
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set. Add it to content_writer/.env or project root .env")
        return Groq(api_key=api_key)
    except ImportError:
        raise ImportError("groq not installed. Run: pip install groq")


def generate_article(system_prompt: str, user_prompt: str, config: dict) -> dict:
    """
    Call Groq and return:
      {
        "content":    str,   # raw markdown output
        "word_count": int,
        "has_frontmatter": bool,
        "has_placeholders": bool,
        "quality_flags": [str],  # any quality warnings
        "tokens_used":   int,
      }
    """
    client = _get_client()

    gen_cfg = config.get("generation", {})
    wmax    = gen_cfg.get("word_count_max", 800)

    # Token budget: ~1.3 tokens per word, add headroom for structure
    max_tokens = min(int(wmax * 1.5) + 500, 3500)

    print(f"    Calling Groq (max_tokens={max_tokens})...")

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.5,   # slightly creative but consistent
            max_tokens=max_tokens,
        )
    except Exception as e:
        raise RuntimeError(f"Groq API call failed: {e}")

    content = response.choices[0].message.content.strip()
    usage   = response.usage

    # Quality checks
    quality_flags = _quality_check(content, config)

    # Enhanced quality gate using orchestrator brief/context
    try:
        from shared.quality_gate import load_enriched_brief, load_competitor_analysis, check_piece
        brief = load_enriched_brief()
        comp_data = load_competitor_analysis()
        if brief:
            gate_flags = check_piece(content, brief, comp_data, api_key=os.getenv("GROQ_API_KEY", ""))
            quality_flags.extend(gate_flags)
    except Exception:
        pass  # Don't fail generation if gate fails

    return {
        "content":          content,
        "word_count":       _count_words(content),
        "has_frontmatter":  content.startswith("---"),
        "has_placeholders": "[PRODUCT_NAME]" in content or "[SHOP_LINK]" in content,
        "quality_flags":    quality_flags,
        "tokens_used":      usage.total_tokens if usage else 0,
        "prompt_tokens":    usage.prompt_tokens if usage else 0,
        "completion_tokens":usage.completion_tokens if usage else 0,
    }


def _count_words(text: str) -> int:
    """Count words, excluding front matter block."""
    # Strip YAML front matter
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            text = text[end + 3:]
    return len(text.split())


def _quality_check(content: str, config: dict) -> list[str]:
    """Return list of quality warning strings."""
    flags = []
    gen_cfg = config.get("generation", {})
    wmin    = gen_cfg.get("word_count_min", 500)
    wmax    = gen_cfg.get("word_count_max", 800)

    word_count = _count_words(content)

    if word_count < wmin:
        flags.append(f"SHORT: {word_count} words (min {wmin})")
    elif word_count > wmax + 200:
        flags.append(f"LONG: {word_count} words (max {wmax})")

    if "[PRODUCT_NAME]" not in content:
        flags.append("MISSING: No [PRODUCT_NAME] placeholder found")

    if "[SHOP_LINK]" not in content:
        flags.append("MISSING: No [SHOP_LINK] CTA found")

    # Check for common AI filler phrases
    filler_phrases = [
        "in today's digital age",
        "in the realm of",
        "it's worth noting",
        "it is important to note",
        "as an ai language model",
        "certainly!",
        "absolutely!",
        "of course!",
        "great question",
    ]
    content_lower = content.lower()
    for phrase in filler_phrases:
        if phrase in content_lower:
            flags.append(f"FILLER: '{phrase}' detected — review this section")

    # Check for made-up specifics (common hallucination patterns)
    hallucination_patterns = [
        r"\$\d+\.\d+",          # specific prices like $49.99
        r"https?://[a-z]+\.[a-z]+/[a-z0-9\-/]+",  # invented URLs
        r"model\s+[A-Z]{2,}\d{3,}",  # made-up model numbers
    ]
    for pat in hallucination_patterns:
        if re.search(pat, content):
            flags.append(f"HALLUCINATION RISK: Pattern '{pat}' found — verify all specific details")
            break  # one warning is enough

    if not content.startswith("---"):
        flags.append("FORMAT: Front matter block missing")

    # Check for required sections
    required_headers = ["##"]
    for h in required_headers:
        if h not in content:
            flags.append("FORMAT: No H2 sections found")
            break

    return flags


def clean_content(content: str) -> str:
    """
    Light cleanup pass:
    - Remove accidental markdown code fence wrappers (```markdown...```)
    - Normalize line endings
    - Ensure front matter is clean
    """
    # Strip outer markdown fences if Groq wrapped the whole thing
    if content.startswith("```markdown"):
        content = content[len("```markdown"):].strip()
    if content.startswith("```"):
        content = content[3:].strip()
    if content.endswith("```"):
        content = content[:-3].strip()

    # Normalize line endings
    content = content.replace("\r\n", "\n").replace("\r", "\n")

    # Collapse 3+ blank lines to 2
    content = re.sub(r"\n{3,}", "\n\n", content)

    return content.strip()
