"""
Location and Geocoding Utilities for CareMap (Nagpur).
Handles distance calculations, OpenStreetMap Nominatim geocoding,
and Overpass API live query integration.
"""

import math
import logging
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Curated coordinates for prominent Nagpur localities (ensures fast, reliable fallbacks)
NAGPUR_LOCALITY_COORDINATES = {
    "dharampeth": (21.1441, 79.0592),
    "sitabuldi": (21.1458, 79.0832),
    "sadar": (21.1589, 79.0782),
    "manish nagar": (21.0952, 79.0754),
    "ramdaspeth": (21.1372, 79.0718),
    "dhantoli": (21.1352, 79.0847),
    "medical square": (21.1278, 79.1002),
    "mihan": (21.0347, 79.0278),
    "mankapur": (21.1963, 79.0768),
    "shankar nagar": (21.1345, 79.0601),
    "khamla": (21.1118, 79.0664),
    "nandanvan": (21.1256, 79.1324),
    "hingna": (21.0967, 78.9881),
    "wardha road": (21.1150, 79.0750),
    "besa": (21.0820, 79.0910),
    "pratap nagar": (21.1205, 79.0558),
    "trimurti nagar": (21.1142, 79.0438),
    "jaripatka": (21.1852, 79.1012),
    "pardi": (21.1450, 79.1620),
    "koradi": (21.2480, 79.0920),
    "central avenue": (21.1558, 79.0963),
}

# In-memory geocode cache
_GEOCODE_CACHE = {}

def calculate_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points on Earth in kilometers.
    """
    radius = 6371.0  # Earth's radius in km

    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)

    a = (math.sin(d_lat / 2.0) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(d_lon / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(radius * c, 2)


def geocode_nagpur_locality(locality_name: str) -> dict:
    """
    Geocode a locality in Nagpur, Maharashtra.
    Tries:
    1. Known curated Nagpur coordinates
    2. In-memory cache
    3. OpenStreetMap Nominatim API
    """
    cleaned = locality_name.strip().lower()
    if not cleaned:
        return {"success": False, "error": "Empty locality query"}

    # 1. Check curated Nagpur localities
    if cleaned in NAGPUR_LOCALITY_COORDINATES:
        lat, lon = NAGPUR_LOCALITY_COORDINATES[cleaned]
        return {
            "success": True,
            "locality": locality_name.title(),
            "latitude": lat,
            "longitude": lon,
            "source": "Curated Nagpur Directory"
        }

    # Partial match in curated list
    for key, coords in NAGPUR_LOCALITY_COORDINATES.items():
        if key in cleaned or cleaned in key:
            return {
                "success": True,
                "locality": key.title(),
                "latitude": coords[0],
                "longitude": coords[1],
                "source": "Curated Nagpur Directory (Fuzzy Match)"
            }

    # 2. Check cache
    if cleaned in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[cleaned]

    # 3. Call Nominatim
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": f"{locality_name}, Nagpur, Maharashtra, India",
            "format": "json",
            "limit": 1
        }
        headers = {
            "User-Agent": "CareMapNagpurHealthApp/1.0 (healthcare-hackathon-research)"
        }
        response = requests.get(url, params=params, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                result = {
                    "success": True,
                    "locality": locality_name.title(),
                    "latitude": float(data[0]["lat"]),
                    "longitude": float(data[0]["lon"]),
                    "source": "OpenStreetMap Nominatim"
                }
                _GEOCODE_CACHE[cleaned] = result
                return result
    except Exception as exc:
        logger.warning(f"Nominatim geocoding failed for {locality_name}: {exc}")

    # Fallback to central Nagpur (Zero Mile / Sitabuldi)
    return {
        "success": False,
        "error": f"Could not precisely geocode '{locality_name}'. Defaulting to Nagpur Center.",
        "locality": "Nagpur Center (Zero Mile)",
        "latitude": 21.1458,
        "longitude": 79.0832,
        "source": "Nagpur Center Fallback"
    }


def fetch_live_osm_nagpur_hospitals() -> list:
    """
    Fetches mapped healthcare facilities from OpenStreetMap via Overpass API.
    Scoped to the greater Nagpur metropolitan bounding box.
    Returns empty list if network is unavailable or times out.
    """
    overpass_url = "https://overpass-api.de/api/interpreter"
    # Bounding box for Nagpur: south, west, north, east
    # Approx: 21.0000, 78.9500 to 21.2600, 79.2000
    query = """
    [out:json][timeout:15];
    (
      node["amenity"="hospital"](21.00,78.95,21.26,79.20);
      way["amenity"="hospital"](21.00,78.95,21.26,79.20);
    );
    out center tags;
    """
    try:
        resp = requests.post(overpass_url, data={"data": query}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            records = []
            for elem in data.get("elements", []):
                tags = elem.get("tags", {})
                name = tags.get("name")
                if not name:
                    continue
                lat = elem.get("lat") or elem.get("center", {}).get("lat")
                lon = elem.get("lon") or elem.get("center", {}).get("lon")
                if not lat or not lon:
                    continue

                phone = tags.get("phone") or tags.get("contact:phone") or "Not listed"
                emergency = tags.get("emergency") == "yes"
                speciality = tags.get("healthcare:speciality") or tags.get("speciality") or "General / Multi-Speciality"
                records.append({
                    "id": f"osm_{elem.get('id')}",
                    "name": name,
                    "locality": tags.get("addr:suburb") or tags.get("addr:city") or "Nagpur",
                    "address": tags.get("addr:street") or tags.get("addr:full") or f"{name}, Nagpur",
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "phone": phone,
                    "specialities": speciality,
                    "emergency_available": emergency,
                    "data_source": "Live OpenStreetMap (Overpass API)",
                    "verification_status": "Community Mapped"
                })
            return records
    except Exception as e:
        logger.warning(f"Overpass live query failed: {e}")
    return []