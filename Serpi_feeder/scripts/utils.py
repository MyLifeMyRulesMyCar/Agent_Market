import json
from fetch_trends import fetch_trends
from parser import simplify_trends


def run(config_path):
    with open(config_path, "r") as f:
        config = json.load(f)

    country = config["country"]
    time_range = config["time_range"]
    markets = config["markets"]

    final_output = {}

    for market, keywords in markets.items():
        print(f"\nProcessing market: {market}")
        final_output[market] = {}

        for keyword in keywords:
            print(f"  Fetching: {keyword}")
            raw = fetch_trends(keyword, country, time_range)
            parsed = simplify_trends(raw)

            final_output[market][keyword] = parsed

    # Save output
    with open("output/trends.json", "w") as f:
        json.dump(final_output, f, indent=4)

    print("\n✅ Trends data saved to output/trends.json")
