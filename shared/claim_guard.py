"""
shared/claim_guard.py — deterministic marketing-claim guard.

The LLM quality gate is good at noticing invented specs, but it treats
competitor comparison and confident performance language as legitimate
marketing copy. Our own gate-1 rules (decisions.md D-001 to D-023) say
otherwise, and those rules do not depend on a model's mood.

This module checks generated copy against rules we can enforce in code:

  * never name or compare a competitor in public copy
  * never assert a feature we have not verified our own board has
  * never state an unmeasured number (TOPS, MB/s, fps, latency, temperature)
  * never mix currencies between the retail and export businesses
  * never use absolute superlatives or guarantee language

Each violation carries a short reason the editor can act on. Findings are
advisory flags for the gate output; nothing here publishes or deletes text.
"""

from __future__ import annotations

import re
from typing import Iterable

# Competitors named in competitor_analysis and market research. Naming one of
# these in public copy is a comparison even without the word "versus".
COMPETITOR_NAMES = [
    "aqara",
    "sonoff",
    "shelly",
    "moes",
    "smartdream",
    "clevr",
    "shinrai",
    "revolution pi",
    "revpi",
    "seeed",
    "recomputer",
    "orange pi",
    "radxa",
]

# A feature only counts as ours when our own product facts say so. The
# injector used to assert whatever the competitor lacked, which is how
# "Mammalia Core Carrier offers Matter support out of the box" got written.
# Patterns are deliberately narrow: "no matter how many sensors" is English,
# not a protocol claim.
UNVERIFIED_FEATURES = [
    (r"\bmatter[-\s]?(ready|support|enabled|compatible|capable|bridge|device|hub)\b", "Matter"),
    (r"\b(supports?|with|built on|via)\s+matter\b", "Matter"),
    (r"\bthread\s+(border|router|network)\b", "Thread"),
    (r"\bzigbee\s+(coordinator|gateway|3\.0|radio)\b", "Zigbee"),
    (r"\bz[-\s]?wave\b", "Z-Wave"),
    (r"\bwi[-\s]?fi\s+6\b", "Wi-Fi 6"),
    (r"\bpower over ethernet\b", "PoE"),
]

SUPERLATIVES = [
    r"\bcheapest\b",
    r"\bfastest\b",
    r"\bworld'?s\b",
    r"\bzero[-\s]?drop\b",
    r"\bnever fails?\b",
    r"\boutperforms?\b",
    r"\boutpaces?\b",
    r"\bbeats? (the|every|all)\b",
    r"\bindustry[-\s]leading\b",
    r"\bcutting[-\s]edge\b",
    r"\bbest[-\s]in[-\s]class\b",
    r"\bunbeatable\b",
]

# Numbers we may not state before they are measured on rev A hardware.
UNMEASURED_NUMBERS = [
    (r"\b\d+(\.\d+)?\s*(tops|mbytes?/s|mb/s|gb/s)\b", "performance figure (needs rev A bench evidence)"),
    (r"\b\d+(\.\d+)?\s*(fps|ms|milliseconds?)\b", "latency or frame-rate figure (needs measurement)"),
    (r"-?\d+\s*(to|–|-)\s*\+?\d+\s*°?\s*c\b", "temperature range (rev A is 0-50 C only)"),
]

# Phrasings that assert a hardware feature we do not have or cannot support.
BANNED_PHRASES = [
    (r"hardware encryption chip", "say 'TPM 2.0 key storage and OS-level measured boot' instead"),
    (r"secure boot with (the )?(encryption|security) chip", "the boot chain of trust is the SoC's, not the chip's"),
    (r"(tpm|encryption|hardware)[-\s]based secure boot", "say 'TPM 2.0 key storage and OS-level measured boot', not secure boot"),
    (r"\bsecure boot\b", "say 'OS-level measured boot'; the boot ROM belongs to the SoM"),
    (r"\bdual[-\s]?(gigabit|gbe|1\s?gb[es]?)\b", "the carrier is '2x GbE, 1 Gbps aggregate', one uplink"),
    (r"\b(even (if|when)|if|when) (one|either) (link|port)[^.]{0,60}(down|fails?|drops?|hiccups?|falters?|dies?)\b", "both GbE ports share one uplink; there is no failover"),
    (r"\b(redundant|failover|fail-safe)\b(?!.*planned)", "no redundancy claim: one uplink, one lane"),
    (r"\bhigh[-\s]?capacity\b", "Squirrel is a branch retention appliance, not high capacity"),
    (r"\b10\s?gb[es]\b", "no 10GbE on the base product"),
    (r"\bout of the box\b", "we cannot assert a feature the competitor lacks as one we ship"),
    (r"\bcertified\b", "no certificate in hand; say 'certification planned'"),
    (r"\bguarantee(s|d)?\b", "no guarantee language: state what the build does"),
]

CURRENCY_RULES = [
    (r"lkr|rs\.?\s?\d", "LKR belongs to elephantronics.lk retail only, never to Mammalia export copy"),
    (r"\$\s?\d", "USD pricing is not set; do not quote a Mammalia price"),
]


def _normalize(text: str) -> str:
    """Fold typographic punctuation so patterns match what the model writes.

    gpt-oss emits U+2011 (non-breaking hyphen) inside words like "dual‑GbE",
    which defeats any regex that expects an ASCII hyphen.
    """
    table = {
        "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-",
        "\u2212": "-", "\u00a0": " ", "\u2019": "'", "\u2018": "'",
        "\u201c": '"', "\u201d": '"', "\u202f": " ",
    }
    return text.translate(str.maketrans(table))


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def _sentence_at(text: str, pos: int) -> str:
    """Return the sentence (or list item) that contains character offset pos."""
    start = max(text.rfind(". ", 0, pos), text.rfind("\n", 0, pos), text.rfind("'", 0, pos))
    start = 0 if start < 0 else start + 1
    ends = [i for i in (text.find(". ", pos), text.find("\n", pos)) if i != -1]
    end = min(ends) if ends else len(text)
    return text[start:end]


def _find(text: str, pattern: str) -> str:
    m = re.search(pattern, text, flags=re.IGNORECASE)
    if not m:
        return ""
    start = max(0, m.start() - 60)
    end = min(len(text), m.end() + 60)
    return text[start:end].replace("\n", " ").strip()


def check_text(text: str, our_features: Iterable[str] | None = None) -> list[dict]:
    """Return a list of {rule, quote, fix} violations for one piece of copy."""
    if not text:
        return []

    violations: list[dict] = []
    text = _normalize(text)
    lowered = text.lower()
    our_features_lower = " ".join(our_features or []).lower()

    for name in COMPETITOR_NAMES:
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            violations.append({
                "rule": "COMPETITOR_NAMED",
                "quote": _find(text, rf"\b{re.escape(name)}\b"),
                "fix": "compare categories, not named competitors",
            })

    for pattern, feature in UNVERIFIED_FEATURES:
        if not re.search(pattern, lowered):
            continue
        if feature.lower() in our_features_lower:
            continue
        violations.append({
            "rule": "UNVERIFIED_FEATURE",
            "quote": _find(text, pattern),
            "fix": f"'{feature}' is not in our verified product facts; describe the platform, do not claim the feature",
        })

    for pattern in SUPERLATIVES:
        if re.search(pattern, lowered):
            violations.append({
                "rule": "ABSOLUTE_CLAIM",
                "quote": _find(text, pattern),
                "fix": "state what the build does; drop the superlative",
            })

    for pattern, reason in UNMEASURED_NUMBERS:
        if re.search(pattern, lowered):
            violations.append({
                "rule": "UNMEASURED_NUMBER",
                "quote": _find(text, pattern),
                "fix": reason,
            })

    for pattern, reason in BANNED_PHRASES:
        for m in re.finditer(pattern, lowered):
            sentence = _sentence_at(lowered, m.start())
            # "Dual-GbE ... 1 Gbps aggregate" states the right number with the
            # wrong name; only the bare claim is a problem.
            if "gbe" in pattern and ("aggregate" in sentence or "1 gbps" in sentence):
                continue
            violations.append({
                "rule": "BANNED_PHRASE",
                "quote": _find(text, pattern),
                "fix": reason,
            })
            break

    for pattern, reason in CURRENCY_RULES:
        if re.search(pattern, lowered):
            violations.append({
                "rule": "CURRENCY",
                "quote": _find(text, pattern),
                "fix": reason,
            })

    # De-duplicate: one flag per rule per piece, keep the first quote, and drop
    # a short quote that is contained in a longer one (e.g. "secure boot" inside
    # "TPM-based secure boot").
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for v in sorted(violations, key=lambda x: len(x["quote"]), reverse=True):
        key = (v["rule"], v["fix"])
        if key in seen:
            continue
        if any(v["quote"] and v["quote"] in other["quote"] for other in unique):
            continue
        seen.add(key)
        unique.append(v)
    return unique


def format_flags(violations: list[dict]) -> list[str]:
    """Render violations as gate-style flag strings."""
    return [
        f"CLAIM_{v['rule']}: '{v['quote']}' — {v['fix']}"
        for v in violations
    ]


def scan_platform_content(content: dict, our_features: Iterable[str] | None = None) -> dict[str, list[str]]:
    """Scan a platform_content_latest.json style payload, per platform."""
    out: dict[str, list[str]] = {}
    for platform, piece in (content.get("platforms") or {}).items():
        if isinstance(piece, str):
            text = piece
        elif isinstance(piece, dict):
            text = " ".join(str(v) for v in piece.values())
        elif isinstance(piece, list):
            text = "\n".join(str(x) for x in piece)
        else:
            continue
        flags = format_flags(check_text(text, our_features))
        if flags:
            out[platform] = flags
    return out


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("shared/platform_content_latest.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    result = scan_platform_content(data)
    print(json.dumps(result, indent=2, ensure_ascii=False))
