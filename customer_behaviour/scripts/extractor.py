"""
scripts/extractor.py — STEP 3: Extract meaningful keywords from cleaned text.

Two strategies:
  1. Domain keyword matching — check for known SBC/hardware terms
  2. Frequency-based extraction — find repeated meaningful tokens

Returns each item with a 'keywords' list appended.
"""

import re
from collections import Counter

# ── Domain keyword list ────────────────────────────────────────
# These are the terms we care about in the SBC / IoT / home automation space
DOMAIN_KEYWORDS = [
    # SBC brands
    "raspberry pi", "orange pi", "radxa", "banana pi", "pine64",
    "rock pi", "rock 5", "khadas", "odroid", "beaglebone",
    "nano pi", "libretech", "libre computer",

    # Chips
    "rk3588", "rk3566", "rk3399", "bcm2712", "bcm2711",
    "esp32", "esp8266", "stm32", "rp2040", "atmega",
    "rockchip", "allwinner", "amlogic", "mediatek",

    # Storage
    "nvme", "emmc", "sd card", "microsd", "ssd", "hdd",
    "m2", "m.2", "sata",

    # Connectivity
    "wifi", "wi-fi", "ethernet", "bluetooth", "zigbee", "zwave",
    "mqtt", "gpio", "uart", "i2c", "spi", "usb", "hdmi",

    # OS / Software
    "armbian", "ubuntu", "debian", "raspbian", "dietpi", "openwrt",
    "home assistant", "esphome", "docker", "kubernetes", "k3s",
    "android", "linux", "kernel", "driver",

    # Use case domains
    "cluster", "nas", "media server", "plex", "jellyfin",
    "smart home", "automation", "vpn", "pihole", "router",
    "retropie", "emulator", "gaming",

    # Issues / hardware
    "overheating", "throttling", "boot", "bootloader", "power",
    "cooling", "heatsink", "fan", "voltage", "firmware",
    "npu", "gpu", "cpu", "ram", "memory",
]

# Pre-sort by length descending so multi-word matches are found first
_SORTED_KW = sorted(DOMAIN_KEYWORDS, key=len, reverse=True)

# Stopwords to ignore in frequency analysis
_STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "have", "from",
    "not", "are", "but", "its", "can", "was", "has", "been",
    "you", "your", "they", "them", "their", "use", "used", "using",
    "get", "got", "just", "also", "like", "than", "then", "when",
    "what", "which", "will", "would", "could", "should", "there",
    "here", "some", "any", "all", "more", "very", "it's", "i'm",
    "my", "me", "we", "our", "so", "if", "or", "at", "in",
    "is", "it", "be", "to", "of", "a", "an", "on", "do",
    "did", "how", "why", "who", "one", "two", "three", "about",
    "tried", "trying", "want", "need", "make", "made", "see",
    "know", "think", "work", "works", "working",
}


def extract_domain_keywords(text: str) -> list[str]:
    """Match known domain keywords in the text."""
    found = []
    remaining = text
    for kw in _SORTED_KW:
        if kw in remaining:
            found.append(kw)
            # Remove matched keyword to avoid sub-matches
            remaining = remaining.replace(kw, " ")
    return list(set(found))


def extract_frequent_tokens(text: str, min_length: int = 4) -> list[str]:
    """Extract individual tokens that are meaningful (not stopwords)."""
    tokens = re.findall(r"\b[a-z][a-z0-9\-]{2,}\b", text)
    meaningful = [
        t for t in tokens
        if t not in _STOPWORDS and len(t) >= min_length
    ]
    # Only return tokens that appear at least twice OR are long enough to be meaningful
    counts = Counter(meaningful)
    return [t for t, c in counts.items() if c >= 1 and len(t) >= min_length]


def extract_keywords(cleaned_items: list[dict]) -> list[dict]:
    """
    Add 'keywords' list to each cleaned item.
    Combines domain keywords + frequent tokens.
    """
    for item in cleaned_items:
        text = item.get("text_clean", "")
        domain_kws  = extract_domain_keywords(text)
        token_kws   = extract_frequent_tokens(text)

        # Merge, domain keywords take priority
        all_kws = list(set(domain_kws + token_kws))
        item["keywords"] = all_kws

    return cleaned_items