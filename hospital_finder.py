"""
Hospital Finder and Directory Engine for CareMap (Nagpur).
Handles dataset loading, deduplication, search filters, and radial sorting.
"""

import os
import re
import pandas as pd
from src.location_utils import calculate_haversine_distance, geocode_nagpur_locality, fetch_live_osm_nagpur_hospitals

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "facilities.csv")

class HospitalFinder:
    def __init__(self, csv_path: str = DATA_PATH):
        self.csv_path = csv_path
        self._cached_hospitals = []
        self.load_data()

    def _normalize_name(self, name: str) -> str:
        """Strip punctuation and common suffixes for clean deduplication."""
        cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", str(name).lower())
        words = [w for w in cleaned.split() if w not in {"hospital", "clinic", "centre", "center", "research", "institute", "and", "the"}]
        return " ".join(words)

    def load_data(self, sync_live_osm: bool = False):
        """Loads data from CSV and optionally merges with live OSM data."""
        records = []
        if os.path.exists(self.csv_path):
            df = pd.read_csv(self.csv_path)
            for _, row in df.iterrows():
                emergency = str(row.get("emergency_available", "False")).lower() in ["true", "1", "yes"]
                records.append({
                    "id": str(row.get("id")),
                    "name": str(row.get("name")),
                    "locality": str(row.get("locality", "Nagpur")),
                    "address": str(row.get("address", "")),
                    "latitude": float(row.get("latitude")),
                    "longitude": float(row.get("longitude")),
                    "phone": str(row.get("phone", "Not listed")),
                    "specialities": str(row.get("specialities", "General Medicine")),
                    "emergency_available": emergency,
                    "data_source": str(row.get("data_source", "CareMap CSV")),
                    "verification_status": str(row.get("verification_status", "Unverified"))
                })

        if sync_live_osm:
            osm_records = fetch_live_osm_nagpur_hospitals()
            records.extend(osm_records)

        # Deduplication: match normalized name or location within 100 meters
        deduped = []
        seen = []
        for r in records:
            norm_name = self._normalize_name(r["name"])
            is_dup = False
            for s in seen:
                dist = calculate_haversine_distance(r["latitude"], r["longitude"], s["latitude"], s["longitude"])
                if (norm_name and norm_name == s["norm_name"]) or (dist < 0.10 and norm_name in s["norm_name"]):
                    is_dup = True
                    break
            if not is_dup:
                seen.append({"norm_name": norm_name, "latitude": r["latitude"], "longitude": r["longitude"]})
                deduped.append(r)

        self._cached_hospitals = deduped

    def get_all_hospitals(self, search: str = "", speciality: str = "", emergency_only: bool = False,
                          source_filter: str = "all", sort_by: str = "name", page: int = 1, page_size: int = 100):
        """Returns citywide hospitals with filtering, sorting, and pagination."""
        results = list(self._cached_hospitals)

        if search:
            q = search.lower().strip()
            results = [h for h in results if q in h["name"].lower() or q in h["locality"].lower() or q in h["address"].lower()]

        if speciality and speciality != "all":
            q_spec = speciality.lower()
            results = [h for h in results if q_spec in h["specialities"].lower()]

        if emergency_only:
            results = [h for h in results if h["emergency_available"] is True]

        if source_filter == "real":
            results = [h for h in results if "Sample" not in h["data_source"]]
        elif source_filter == "sample":
            results = [h for h in results if "Sample" in h["data_source"]]

        if sort_by == "name":
            results.sort(key=lambda x: x["name"])
        elif sort_by == "locality":
            results.sort(key=lambda x: x["locality"])

        total = len(results)
        start = (page - 1) * page_size
        paginated = results[start:start + page_size]

        # Add Google Maps directions links
        for h in paginated:
            h["directions_url"] = f"https://www.google.com/maps/dir/?api=1&destination={h['latitude']},{h['longitude']}"

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "hospitals": paginated
        }

    def search_by_locality(self, locality_name: str, radius_km: float = 10.0, speciality: str = "", emergency_only: bool = False):
        """Locality-based search: geocodes locality and retrieves facilities within radius."""
        geocode_result = geocode_nagpur_locality(locality_name)
        lat = geocode_result.get("latitude", 21.1458)
        lon = geocode_result.get("longitude", 79.0832)

        return self.search_nearby(lat, lon, radius_km, speciality, emergency_only, reference_label=geocode_result.get("locality", locality_name))

    def search_nearby(self, lat: float, lon: float, radius_km: float = 10.0, speciality: str = "",
                      emergency_only: bool = False, reference_label: str = "Current Location"):
        """Locates hospitals within radius_km from coordinates and sorts by distance."""
        matches = []
        for h in self._cached_hospitals:
            if emergency_only and not h["emergency_available"]:
                continue
            if speciality and speciality != "all" and speciality.lower() not in h["specialities"].lower():
                continue

            dist = calculate_haversine_distance(lat, lon, h["latitude"], h["longitude"])
            if dist <= radius_km:
                item = dict(h)
                item["distance_km"] = dist
                item["directions_url"] = f"https://www.google.com/maps/dir/?api=1&destination={h['latitude']},{h['longitude']}"
                matches.append(item)

        matches.sort(key=lambda x: x["distance_km"])

        return {
            "search_center": {
                "latitude": lat,
                "longitude": lon,
                "label": reference_label,
                "radius_km": radius_km
            },
            "count": len(matches),
            "hospitals": matches
        }

    def get_known_localities(self):
        """Lists localities and count of hospitals per locality."""
        counts = {}
        for h in self._cached_hospitals:
            loc = h.get("locality", "Other").title()
            counts[loc] = counts.get(loc, 0) + 1
        return sorted([{"locality": k, "count": v} for k, v in counts.items()], key=lambda x: x["count"], reverse=True)