"""
clusterer.py — Group scored keywords into semantic clusters.
Simple overlap-based clustering, no ML needed.
"""

CLUSTERS = {
    "storage":    ["nvme", "ssd", "emmc", "sd card", "storage", "disk", "filesystem"],
    "boot":       ["boot", "bootloader", "startup", "u-boot", "flash"],
    "networking": ["wifi", "ethernet", "bluetooth", "network", "connection", "mqtt"],
    "power":      ["power", "voltage", "overheating", "throttle", "psu", "watt"],
    "software":   ["driver", "kernel", "os", "ubuntu", "armbian", "install", "package"],
    "display":    ["hdmi", "display", "screen", "resolution", "monitor", "4k"],
    "ai_ml":      ["npu", "ai", "inference", "llm", "neural", "rknn", "tops"],
    "home_auto":  ["home assistant", "esphome", "zigbee", "smart home", "mqtt", "tasmota"],
    "cluster":    ["kubernetes", "k3s", "docker", "cluster", "ceph"],
    "solar":      ["solar", "inverter", "mppt", "lifepo4", "off grid", "battery"],
}


def assign_cluster(keyword: str) -> str:
    kw = keyword.lower()
    best = "general"
    best_hits = 0
    for cluster, terms in CLUSTERS.items():
        hits = sum(1 for t in terms if t in kw)
        if hits > best_hits:
            best_hits = hits
            best = cluster
    return best


def cluster_keywords(scored: list[dict]) -> list[dict]:
    for item in scored:
        item["cluster"] = assign_cluster(item["keyword"])
    return scored


def build_cluster_summary(scored: list[dict]) -> dict:
    """Group by cluster for dashboard display."""
    from collections import defaultdict
    groups: dict = defaultdict(list)
    for item in scored:
        groups[item["cluster"]].append(item)
    return {
        cluster: sorted(items, key=lambda x: x["score"], reverse=True)
        for cluster, items in sorted(groups.items())
    }