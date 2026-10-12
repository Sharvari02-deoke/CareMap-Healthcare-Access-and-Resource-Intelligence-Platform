"""
CareMap — Healthcare Access & Resource Intelligence Platform
Nagpur, Maharashtra, India.
Flask Backend Application.
"""

import os
import logging
from flask import Flask, render_template, request, jsonify
from src.hospital_finder import HospitalFinder
from src.gap_analysis import HealthcareGapAnalyzer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CareMap")

app = Flask(__name__)

# Initialize Hospital Finder Engine
finder = HospitalFinder()

@app.route("/")
def index():
    """Renders the main CareMap healthcare intelligence dashboard."""
    return render_template("index.html")


@app.route("/api/all-hospitals", methods=["GET"])
def api_all_hospitals():
    """
    Returns citywide mapped hospitals across Nagpur.
    Query parameters:
    - search: text query (name, locality, address)
    - speciality: speciality filter
    - emergency_only: true/false
    - source: all / real / sample
    - sort_by: name / locality
    - page: page number (default 1)
    - page_size: items per page (default 100)
    """
    try:
        search = request.args.get("search", "").strip()
        speciality = request.args.get("speciality", "all").strip()
        emergency_only = request.args.get("emergency_only", "false").lower() in ["true", "1", "yes"]
        source_filter = request.args.get("source", "all").strip()
        sort_by = request.args.get("sort_by", "name").strip()
        page = max(1, int(request.args.get("page", 1)))
        page_size = max(1, min(200, int(request.args.get("page_size", 100))))

        result = finder.get_all_hospitals(
            search=search,
            speciality=speciality,
            emergency_only=emergency_only,
            source_filter=source_filter,
            sort_by=sort_by,
            page=page,
            page_size=page_size
        )
        return jsonify({"status": "success", "data": result}), 200
    except Exception as e:
        logger.error(f"Error in /api/all-hospitals: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Failed to retrieve hospitals", "details": str(e)}), 500


@app.route("/api/search-locality", methods=["GET"])
def api_search_locality():
    """
    Searches hospitals around a given Nagpur locality within a specified radius.
    Query parameters:
    - locality: name of the locality (e.g., Dharampeth, Sitabuldi)
    - radius: search radius in km (default 10, max 50)
    - speciality: optional speciality filter
    - emergency_only: true/false
    """
    try:
        locality = request.args.get("locality", "").strip()
        if not locality:
            return jsonify({"status": "error", "message": "Query parameter 'locality' is required"}), 400

        try:
            radius = float(request.args.get("radius", 10.0))
            if radius <= 0 or radius > 50:
                radius = 10.0
        except ValueError:
            radius = 10.0

        speciality = request.args.get("speciality", "all").strip()
        emergency_only = request.args.get("emergency_only", "false").lower() in ["true", "1", "yes"]

        result = finder.search_by_locality(
            locality_name=locality,
            radius_km=radius,
            speciality=speciality,
            emergency_only=emergency_only
        )
        return jsonify({"status": "success", "data": result}), 200
    except Exception as e:
        logger.error(f"Error in /api/search-locality: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Locality search failed", "details": str(e)}), 500


@app.route("/api/nearby-hospitals", methods=["GET"])
def api_nearby_hospitals():
    """
    Finds hospitals near given coordinates (from browser Geolocation API).
    Query parameters:
    - lat: latitude (float)
    - lon: longitude (float)
    - radius: search radius in km (default 10)
    - speciality: optional speciality filter
    - emergency_only: true/false
    """
    try:
        lat_str = request.args.get("lat")
        lon_str = request.args.get("lon")

        if not lat_str or not lon_str:
            return jsonify({"status": "error", "message": "Both 'lat' and 'lon' query parameters are required"}), 400

        try:
            lat = float(lat_str)
            lon = float(lon_str)
        except ValueError:
            return jsonify({"status": "error", "message": "Invalid coordinates provided"}), 400

        try:
            radius = float(request.args.get("radius", 10.0))
            if radius <= 0 or radius > 50:
                radius = 10.0
        except ValueError:
            radius = 10.0

        speciality = request.args.get("speciality", "all").strip()
        emergency_only = request.args.get("emergency_only", "false").lower() in ["true", "1", "yes"]

        result = finder.search_nearby(
            lat=lat,
            lon=lon,
            radius_km=radius,
            speciality=speciality,
            emergency_only=emergency_only,
            reference_label="User Geolocation"
        )
        return jsonify({"status": "success", "data": result}), 200
    except Exception as e:
        logger.error(f"Error in /api/nearby-hospitals: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Nearby search failed", "details": str(e)}), 500


@app.route("/api/areas", methods=["GET"])
def api_areas():
    """Returns all mapped localities and their hospital counts."""
    try:
        areas = finder.get_known_localities()
        return jsonify({"status": "success", "data": areas}), 200
    except Exception as e:
        logger.error(f"Error in /api/areas: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Failed to fetch area data"}), 500


@app.route("/api/analysis", methods=["GET"])
def api_analysis():
    """Generates the healthcare access, distribution, and gap intelligence dashboard data."""
    try:
        analyzer = HealthcareGapAnalyzer(finder._cached_hospitals)
        report = analyzer.run_comprehensive_analysis()
        return jsonify({"status": "success", "data": report}), 200
    except Exception as e:
        logger.error(f"Error in /api/analysis: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Analysis failed", "details": str(e)}), 500


@app.route("/api/refresh-osm", methods=["POST"])
def api_refresh_osm():
    """Triggers a live sync with OpenStreetMap Overpass API for Nagpur."""
    try:
        finder.load_data(sync_live_osm=True)
        return jsonify({
            "status": "success",
            "message": "Live OSM hospital query completed and cached.",
            "total_records": len(finder._cached_hospitals)
        }), 200
    except Exception as e:
        logger.error(f"Error refreshing OSM data: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "OSM refresh failed", "details": str(e)}), 500


@app.errorhandler(404)
def not_found(e):
    return jsonify({"status": "error", "message": "Endpoint not found"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"status": "error", "message": "Internal server error"}), 500


if __name__ == "__main__":
    # Runs locally on port 5000
    app.run(host="127.0.0.1", port=5000, debug=True)