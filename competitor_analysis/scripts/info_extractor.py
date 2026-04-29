"""
scripts/info_extractor.py — Extract structured product info from Vector DB docs
and pre-configured known features.

Extracts:
  - product name
  - detected features (from text + known list)
  - detected limitations / missing features
  - price (if found in text)
  - SoC / chip name
  - RAM options
  - storage options
"""

import re
from typing import Optional


# ── Patterns for extracting hardware specs ────────────────────

_PRICE_PATTERNS = [
    r"\$\s*(\d+(?:\.\d{2})?)",
    r"USD\s*(\d+(?:\.\d{2})?)",
    r"(\d+(?:\.\d{2})?)\s*USD",
    r"price[:\s]+(\d+)",
]

_RAM_PATTERNS = [
    r"(\d+)\s*GB\s*(?:LPDDR\d|RAM|memory|DRAM)",
    r"(?:up to|max)\s*(\d+)\s*GB",
    r"(\d+)\s*GB\s+(?:RAM|memory)",
]

_SOC_KEYWORDS = [
    "RK3588", "RK3588S", "RK3566", "RK3576", "BCM2712", "BCM2711",
    "Amlogic A311D2", "Amlogic S922X", "MT8395", "RK3308", "ESP32",
    "Allwinner H618", "Allwinner H6",
]

_FEATURE_KEYWORDS = {
    "NVMe support":        ["nvme", "m.2 m-key", "pcie nvme", "m2 nvme"],
    "PCIe":                ["pcie", "pci express", "pci-e"],
    "USB 3.0":             ["usb 3.0", "usb 3.1", "usb 3.2", "usb-c 3", "superspeed usb"],
    "HDMI output":         ["hdmi"],
    "4K video output":     ["4k", "3840x2160", "uhd"],
    "Wi-Fi":               ["wi-fi", "wifi", "wireless"],
    "Wi-Fi 6":             ["wi-fi 6", "wifi 6", "802.11ax", "ax200", "ax201"],
    "Bluetooth":           ["bluetooth"],
    "GPIO pins":           ["gpio", "40-pin", "26-pin", "gpio header"],
    "eMMC":                ["emmc"],
    "NPU / AI accelerator":["npu", "ai accelerator", "neural", "rknn", "6tops", "tops"],
    "dual Ethernet":       ["dual ethernet", "dual gigabit", "2x ethernet", "two ethernet"],
    "PoE":                 ["poe", "power over ethernet"],
    "active cooling":      ["active cooling", "fan", "heatsink with fan"],
    "USB-C power":         ["usb-c power", "type-c power", "pd charging"],
}

_LIMITATION_SIGNALS = [
    ("no NVMe",       ["no nvme", "no m.2", "without nvme"]),
    ("USB 2.0 only",  ["usb 2.0 only", "no usb 3"]),
    ("no Wi-Fi",      ["no wifi", "no wi-fi", "without wifi", "wired only"]),
    ("no HDMI",       ["no hdmi", "without hdmi"]),
    ("limited RAM",   ["512mb", "256mb", "1gb ram", "1gb lpddr"]),
    ("no GPIO",       ["no gpio", "no expansion header"]),
    ("no PCIe",       ["no pcie", "no pci express"]),
    ("ARM 32-bit",    ["armv7", "cortex-a7", "cortex-a9"]),
]


def _scan_text(text: str, patterns: list[str]) -> bool:
    """Check if any pattern matches the lowercase text."""
    text_lower = text.lower()
    return any(p in text_lower for p in patterns)


def _extract_price_from_text(text: str) -> Optional[float]:
    """Try to extract a price from free text."""
    for pat in _PRICE_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
    return None


def _extract_ram_from_text(text: str) -> Optional[int]:
    """Extract max RAM value in GB."""
    max_ram = 0
    for pat in _RAM_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            try:
                val = int(m.group(1))
                if 1 <= val <= 128:  # sanity check
                    max_ram = max(max_ram, val)
            except ValueError:
                pass
    return max_ram if max_ram > 0 else None


def _extract_soc_from_text(text: str) -> Optional[str]:
    """Find SoC name in text."""
    text_upper = text.upper()
    for soc in _SOC_KEYWORDS:
        if soc.upper() in text_upper:
            return soc
    return None


def extract_product_info(
    competitor_name: str,
    known_features: list[str],
    vector_docs: list[dict],
    known_price: Optional[float] = None,
) -> dict:
    """
    Combine known features (from YAML) with info extracted from Vector DB docs.

    Returns:
      {
        "name":        str,
        "soc":         str | None,
        "max_ram_gb":  int | None,
        "price_usd":   float | None,
        "features":    [str],
        "limitations": [str],
        "raw_snippets":[str],   # key text excerpts from vector docs
      }
    """
    # Combine all vector doc text into one blob
    combined_text = " ".join(d.get("text", "") for d in vector_docs)
    combined_lower = combined_text.lower()

    # Also combine known features for scanning
    known_text = " ".join(known_features).lower()
    full_text  = combined_lower + " " + known_text

    # ── Detect features ───────────────────────────────────────
    detected_features = set()

    # From known features list (pre-configured)
    for feat in known_features:
        feat_lower = feat.lower()
        # Map known feature text to canonical feature names
        for canonical, patterns in _FEATURE_KEYWORDS.items():
            if any(p in feat_lower for p in patterns):
                detected_features.add(canonical)

    # From vector doc text
    for canonical, patterns in _FEATURE_KEYWORDS.items():
        if _scan_text(full_text, patterns):
            detected_features.add(canonical)

    # ── Detect limitations ────────────────────────────────────
    detected_limitations = []
    for label, patterns in _LIMITATION_SIGNALS:
        if _scan_text(full_text, patterns):
            detected_limitations.append(label)

    # ── Extract structured fields ─────────────────────────────
    soc     = _extract_soc_from_text(combined_text + " " + " ".join(known_features))
    max_ram = _extract_ram_from_text(combined_text + " " + " ".join(known_features))
    price   = known_price

    # Try to extract price from text if not provided
    if price is None:
        price = _extract_price_from_text(combined_text)

    # ── Top snippets from vector docs ─────────────────────────
    snippets = []
    for doc in sorted(vector_docs, key=lambda d: d.get("score", 0), reverse=True)[:3]:
        snippet = doc.get("text", "")[:300].strip()
        if snippet:
            snippets.append({
                "text":   snippet,
                "source": doc.get("source", ""),
                "score":  doc.get("score", 0),
            })

    return {
        "name":        competitor_name,
        "soc":         soc,
        "max_ram_gb":  max_ram,
        "price_usd":   price,
        "features":    sorted(detected_features),
        "limitations": detected_limitations,
        "raw_snippets": snippets,
    }