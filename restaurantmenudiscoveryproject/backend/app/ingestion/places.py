"""Restaurant discovery via Google Places API (New) and Geocoding API."""

import requests

from app.config import settings

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
NEARBY_SEARCH_URL = "https://places.googleapis.com/v1/places:searchNearby"

# Only request the fields we actually use to keep cost minimal.
FIELD_MASK = "places.id,places.displayName,places.formattedAddress,places.websiteUri,places.location"


def geocode_area(query: str) -> tuple[float, float]:
    resp = requests.get(
        GEOCODE_URL, params={"address": query, "key": settings.google_maps_api_key}, timeout=10
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("results"):
        raise RuntimeError(f"No geocode result for '{query}': {data.get('status')}")
    loc = data["results"][0]["geometry"]["location"]
    return loc["lat"], loc["lng"]


def find_restaurants(lat: float, lng: float, radius_m: int) -> list[dict]:
    body = {
        "includedTypes": ["restaurant"],
        "maxResultCount": 20,
        "locationRestriction": {
            "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": radius_m}
        },
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_maps_api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    resp = requests.post(NEARBY_SEARCH_URL, json=body, headers=headers, timeout=10)
    resp.raise_for_status()
    places = resp.json().get("places", [])

    return [
        {
            "place_id": p["id"],
            "name": p.get("displayName", {}).get("text", ""),
            "address": p.get("formattedAddress", ""),
            "lat": p.get("location", {}).get("latitude"),
            "lng": p.get("location", {}).get("longitude"),
            "website": p.get("websiteUri"),
        }
        for p in places
    ]
