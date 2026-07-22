"""
Throwaway sanity-check script: for each test area, find nearby restaurants
and report how many expose a website (a proxy for "can we find a menu?").

Usage:
    export GOOGLE_MAPS_API_KEY="your-key-here"
    python scripts/places_scan.py
"""

import csv
import os
import sys

import requests

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
NEARBY_SEARCH_URL = "https://places.googleapis.com/v1/places:searchNearby"

AREAS = [
    {"label": "galleria_houston", "query": "The Galleria, Houston, TX", "radius_m": 1500},
    {"label": "zip_77004", "query": "77004", "radius_m": 2000},
]

FIELD_MASK = "places.displayName,places.formattedAddress,places.websiteUri,places.types"


def geocode(api_key: str, query: str) -> tuple[float, float]:
    resp = requests.get(GEOCODE_URL, params={"address": query, "key": api_key}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("results"):
        raise RuntimeError(f"No geocode result for '{query}': {data.get('status')}")
    loc = data["results"][0]["geometry"]["location"]
    return loc["lat"], loc["lng"]


def nearby_restaurants(api_key: str, lat: float, lng: float, radius_m: int) -> list[dict]:
    body = {
        "includedTypes": ["restaurant"],
        "maxResultCount": 20,
        "locationRestriction": {
            "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": radius_m}
        },
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    resp = requests.post(NEARBY_SEARCH_URL, json=body, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json().get("places", [])


def main() -> None:
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        sys.exit("Set GOOGLE_MAPS_API_KEY before running this script.")

    out_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(out_dir, exist_ok=True)

    for area in AREAS:
        lat, lng = geocode(api_key, area["query"])
        places = nearby_restaurants(api_key, lat, lng, area["radius_m"])

        with_site = [p for p in places if p.get("websiteUri")]
        print(f"\n{area['label']} ({area['query']}) @ {lat:.5f},{lng:.5f}")
        print(f"  restaurants found: {len(places)}")
        print(f"  with a website:    {len(with_site)}")

        out_path = os.path.join(out_dir, f"{area['label']}.csv")
        with open(out_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["name", "address", "website"])
            for p in places:
                writer.writerow(
                    [
                        p.get("displayName", {}).get("text", ""),
                        p.get("formattedAddress", ""),
                        p.get("websiteUri", ""),
                    ]
                )
        print(f"  wrote {out_path}")


if __name__ == "__main__":
    main()
