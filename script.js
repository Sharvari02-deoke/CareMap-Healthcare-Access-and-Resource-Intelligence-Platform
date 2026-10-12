/* -------------------------------------------------------------
   CareMap — Frontend Client Script
   Handles Leaflet map rendering, Geolocation, Locality Search,
   Backend API integration, synchronization & analytics tabs.
   ------------------------------------------------------------- */

let map = null;
let markersLayer = null;
let currentHospitals = [];
let userLocationMarker = null;

const NAGPUR_CENTER = [21.1458, 79.0832]; // Zero Mile / Central Nagpur

document.addEventListener("DOMContentLoaded", () => {
  initMap();
  setupEventListeners();
  setupTabs();
  loadAllHospitals();
  loadAnalytics();
});

/* Initialize Leaflet Map */
function initMap() {
  map = L.map("leafletMap").setView(NAGPUR_CENTER, 12);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);

  markersLayer = L.layerGroup().addTo(map);
}

/* Event Handlers */
function setupEventListeners() {
  // Locality Search
  document.getElementById("searchLocalityBtn").addEventListener("click", performLocalitySearch);
  document.getElementById("localityInput").addEventListener("keypress", (e) => {
    if (e.key === "Enter") performLocalitySearch();
  });

  // Browser Geolocation
  document.getElementById("useLocationBtn").addEventListener("click", getUserLocation);

  // View All City
  document.getElementById("viewAllBtn").addEventListener("click", () => {
    document.getElementById("localityInput").value = "";
    loadAllHospitals();
  });

  // Reset Search
  document.getElementById("resetSearchBtn").addEventListener("click", () => {
    document.getElementById("localityInput").value = "";
    document.getElementById("specialityFilter").value = "all";
    document.getElementById("sourceFilter").value = "real";
    document.getElementById("emergencyOnlyCheckbox").checked = false;
    loadAllHospitals();
  });

  // Filters & Sorting
  document.getElementById("specialityFilter").addEventListener("change", applyFiltersAndSort);
  document.getElementById("sourceFilter").addEventListener("change", applyFiltersAndSort);
  document.getElementById("emergencyOnlyCheckbox").addEventListener("change", applyFiltersAndSort);
  document.getElementById("sortSelect").addEventListener("change", applyFiltersAndSort);

  // Sync OSM Button
  document.getElementById("refreshOsmBtn").addEventListener("click", triggerOsmSync);

  // Modal Close
  document.getElementById("modalCloseBtn").addEventListener("click", closeModal);
  document.getElementById("hospitalModal").addEventListener("click", (e) => {
    if (e.target.id === "hospitalModal") closeModal();
  });
}

/* Navigation Tabs */
function setupTabs() {
  const tabs = document.querySelectorAll(".tab-btn");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      tabs.forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));

      tab.classList.add("active");
      const targetId = tab.getAttribute("data-tab");
      document.getElementById(targetId).classList.add("active");

      if (targetId === "directoryTab" && map) {
        setTimeout(() => map.invalidateSize(), 200);
      }
    });
  });
}

/* API Calls */
async function loadAllHospitals() {
  showLoader(true);
  updateActiveFilterLabel("All Nagpur Mapped Hospitals");
  try {
    const speciality = document.getElementById("specialityFilter").value;
    const source = document.getElementById("sourceFilter").value;
    const emergencyOnly = document.getElementById("emergencyOnlyCheckbox").checked;

    const url = `/api/all-hospitals?speciality=${speciality}&source=${source}&emergency_only=${emergencyOnly}`;
    const resp = await fetch(url);
    const json = await resp.json();

    if (json.status === "success") {
      currentHospitals = json.data.hospitals;
      renderHospitals(currentHospitals);
      renderMapMarkers(currentHospitals);
    }
  } catch (err) {
    console.error("Error loading all hospitals:", err);
  } finally {
    showLoader(false);
  }
}

async function performLocalitySearch() {
  const locality = document.getElementById("localityInput").value.trim();
  if (!locality) {
    loadAllHospitals();
    return;
  }

  showLoader(true);
  const radius = document.getElementById("radiusSelect").value;
  const speciality = document.getElementById("specialityFilter").value;
  const emergencyOnly = document.getElementById("emergencyOnlyCheckbox").checked;

  updateActiveFilterLabel(`Locality: ${locality} (${radius} km radius)`);

  try {
    const url = `/api/search-locality?locality=${encodeURIComponent(locality)}&radius=${radius}&speciality=${speciality}&emergency_only=${emergencyOnly}`;
    const resp = await fetch(url);
    const json = await resp.json();

    if (json.status === "success") {
      currentHospitals = json.data.hospitals;
      renderHospitals(currentHospitals);
      renderMapMarkers(currentHospitals, json.data.search_center);
    }
  } catch (err) {
    console.error("Locality search failed:", err);
  } finally {
    showLoader(false);
  }
}

function getUserLocation() {
  if (!navigator.geolocation) {
    alert("Geolocation is not supported by your browser. Please enter your locality manually.");
    return;
  }

  showLoader(true);
  navigator.geolocation.getCurrentPosition(
    async (pos) => {
      const lat = pos.coords.latitude;
      const lon = pos.coords.longitude;
      const radius = document.getElementById("radiusSelect").value;
      const speciality = document.getElementById("specialityFilter").value;
      const emergencyOnly = document.getElementById("emergencyOnlyCheckbox").checked;

      updateActiveFilterLabel(`Nearby My Location (${radius} km radius)`);

      try {
        const url = `/api/nearby-hospitals?lat=${lat}&lon=${lon}&radius=${radius}&speciality=${speciality}&emergency_only=${emergencyOnly}`;
        const resp = await fetch(url);
        const json = await resp.json();

        if (json.status === "success") {
          currentHospitals = json.data.hospitals;
          renderHospitals(currentHospitals);
          renderMapMarkers(currentHospitals, { latitude: lat, longitude: lon, label: "My Location", radius_km: radius });
        }
      } catch (e) {
        console.error("Nearby search failed:", e);
      } finally {
        showLoader(false);
      }
    },
    (error) => {
      showLoader(false);
      let msg = "Could not retrieve your location. ";
      if (error.code === error.PERMISSION_DENIED) {
        msg += "Permission was denied. Please enter a locality name manually.";
      } else if (error.code === error.TIMEOUT) {
        msg += "The location request timed out.";
      } else {
        msg += "Location information is unavailable.";
      }
      alert(msg);
    },
    { timeout: 8000 }
  );
}

function applyFiltersAndSort() {
  const query = document.getElementById("localityInput").value.trim();
  if (query) {
    performLocalitySearch();
  } else {
    loadAllHospitals();
  }
}

/* Rendering Map Markers */
function renderMapMarkers(hospitals, centerInfo = null) {
  markersLayer.clearLayers();

  if (centerInfo) {
    // User or Search Center marker
    const centerIcon = L.divIcon({
      className: "custom-center-icon",
      html: `<div style="background-color: #0284c7; width: 14px; height: 14px; border: 2px solid #fff; border-radius: 50%; box-shadow: 0 0 6px #0284c7;"></div>`
    });

    userLocationMarker = L.marker([centerInfo.latitude, centerInfo.longitude], { icon: centerIcon })
      .bindPopup(`<strong>${centerInfo.label}</strong><br>Radius: ${centerInfo.radius_km || 10} km`)
      .addTo(markersLayer);

    // Circle showing radius
    if (centerInfo.radius_km) {
      L.circle([centerInfo.latitude, centerInfo.longitude], {
        radius: centerInfo.radius_km * 1000,
        color: "#0284c7",
        fillColor: "#0284c7",
        fillOpacity: 0.08,
        weight: 1.5
      }).addTo(markersLayer);
    }
  }

  const bounds = [];

  hospitals.forEach(h => {
    let pinColor = "#0d9488"; // Teal for standard
    if (h.emergency_available) pinColor = "#ef4444"; // Red for emergency
    if (h.data_source && h.data_source.includes("Sample")) pinColor = "#f59e0b"; // Amber for simulation

    const markerIcon = L.divIcon({
      className: "custom-marker-icon",
      html: `<div style="background-color: ${pinColor}; width: 12px; height: 12px; border: 2px solid #ffffff; border-radius: 50%; box-shadow: 0 2px 4px rgba(0,0,0,0.3);"></div>`
    });

    const marker = L.marker([h.latitude, h.longitude], { icon: markerIcon }).addTo(markersLayer);
    bounds.push([h.latitude, h.longitude]);

    const popupHtml = `
      <div style="font-family: inherit; font-size: 0.825rem; min-width: 180px;">
        <strong style="color: #0f172a; font-size: 0.9rem;">${h.name}</strong><br>
        <span style="color: #64748b;">${h.locality}</span><br>
        ${h.emergency_available ? '<span style="color: #ef4444; font-weight: 600;">🚨 24/7 Emergency Listed</span><br>' : ''}
        ${h.phone && h.phone !== 'Not listed' ? `<span>📞 ${h.phone}</span><br>` : ''}
        <div style="margin-top: 6px;">
          <a href="${h.directions_url}" target="_blank" rel="noopener" style="color: #0d9488; font-weight: 600; text-decoration: none;">Get Directions &rarr;</a>
        </div>
      </div>
    `;
    marker.bindPopup(popupHtml);
  });

  if (bounds.length > 0) {
    map.fitBounds(bounds, { padding: [30, 30], maxZoom: 14 });
  } else if (centerInfo) {
    map.setView([centerInfo.latitude, centerInfo.longitude], 13);
  }
}

/* Rendering Hospital Cards */
function renderHospitals(hospitals) {
  const container = document.getElementById("hospitalList");
  const countLabel = document.getElementById("resultCountLabel");
  const emptyState = document.getElementById("emptyState");

  container.innerHTML = "";

  if (!hospitals || hospitals.length === 0) {
    emptyState.style.display = "flex";
    countLabel.textContent = "0 facilities found";
    return;
  }

  emptyState.style.display = "none";
  countLabel.textContent = `Showing ${hospitals.length} healthcare facilities`;

  hospitals.forEach(h => {
    const card = document.createElement("div");
    card.className = "hospital-card";

    // Split specialities into chips
    const specChips = (h.specialities || "General Medicine")
      .split(";")
      .slice(0, 3)
      .map(s => `<span class="spec-chip">${s.trim()}</span>`)
      .join("");

    const isSample = h.data_source && h.data_source.includes("Sample");
    const distBadge = h.distance_km !== undefined ? `<span class="badge badge-dist">${h.distance_km} km away</span>` : "";

    card.innerHTML = `
      <div class="card-top">
        <h4 class="hospital-name">${h.name}</h4>
        <div class="card-badges">
          ${distBadge}
          ${h.emergency_available ? '<span class="badge badge-emergency">Emergency</span>' : ''}
          ${isSample ? '<span class="badge badge-sample">Sample Simulation</span>' : '<span class="badge badge-verified">Verified</span>'}
        </div>
      </div>
      <p class="hospital-address">📍 ${h.address || h.locality}</p>
      <div class="hospital-specs">${specChips}</div>
      <div class="card-actions">
        <div>
          ${h.phone && h.phone !== "Not listed" ? `<a href="tel:${h.phone}" class="phone-link">📞 ${h.phone}</a>` : '<span style="color: #94a3b8;">Phone: Not listed</span>'}
        </div>
        <a href="${h.directions_url}" target="_blank" rel="noopener" class="directions-btn" onclick="event.stopPropagation();">
          Directions ↗
        </a>
      </div>
    `;

    // Click card to zoom map
    card.addEventListener("click", () => {
      map.setView([h.latitude, h.longitude], 15);
      showHospitalModal(h);
    });

    container.appendChild(card);
  });
}

/* Hospital Detail Modal */
function showHospitalModal(h) {
  const modal = document.getElementById("hospitalModal");
  const content = document.getElementById("modalContent");

  const isSample = h.data_source && h.data_source.includes("Sample");

  content.innerHTML = `
    <h3 style="color: #0f172a; margin-bottom: 0.5rem;">${h.name}</h3>
    <p style="color: #64748b; font-size: 0.85rem; margin-bottom: 1rem;">📍 ${h.address || h.locality}</p>
    
    <div style="display: flex; gap: 0.5rem; margin-bottom: 1rem; flex-wrap: wrap;">
      ${h.emergency_available ? '<span class="badge badge-emergency">24/7 Emergency Ready</span>' : ''}
      ${isSample ? '<span class="badge badge-sample">Sample Simulation Record</span>' : '<span class="badge badge-verified">Verified Landmark</span>'}
      <span class="badge" style="background: #f1f5f9; color: #475569;">Source: ${h.data_source}</span>
    </div>

    <div style="margin-bottom: 1rem; font-size: 0.85rem;">
      <strong>Listed Specialities:</strong>
      <div style="margin-top: 0.4rem; display: flex; flex-wrap: wrap; gap: 0.35rem;">
        ${(h.specialities || "General Medicine").split(";").map(s => `<span class="spec-chip">${s.trim()}</span>`).join("")}
      </div>
    </div>

    <div style="font-size: 0.85rem; margin-bottom: 1.25rem;">
      <strong>Contact:</strong> ${h.phone && h.phone !== 'Not listed' ? `<a href="tel:${h.phone}" style="color: #0d9488;">${h.phone}</a>` : 'Not listed'}
    </div>

    <div style="display: flex; gap: 0.75rem;">
      <a href="${h.directions_url}" target="_blank" rel="noopener" class="btn btn-teal" style="flex: 1; text-decoration: none;">
        Open in Google Maps
      </a>
      <button class="btn btn-outline" onclick="closeModal()">Close</button>
    </div>
  `;

  modal.classList.add("open");
}

function closeModal() {
  document.getElementById("hospitalModal").classList.remove("open");
}

/* Load Analytics & Gap Intelligence */
async function loadAnalytics() {
  try {
    const resp = await fetch("/api/analysis");
    const json = await resp.json();
    if (json.status !== "success") return;

    const data = json.data;

    // Metric Summary Cards
    document.getElementById("statTotalHospitals").textContent = data.summary.total_records;
    document.getElementById("statEmergencyCount").textContent = `${data.summary.emergency_capable_count} (${data.summary.emergency_capable_pct}%)`;
    if (data.locality_distribution.length > 0) {
      document.getElementById("statTopLocality").textContent = `${data.locality_distribution[0].locality}`;
    }
    document.getElementById("statDataCompleteness").textContent = `${data.summary.data_completeness.phone_available_pct}%`;

    // Distribution Bars
    const barsContainer = document.getElementById("localityBars");
    barsContainer.innerHTML = "";
    const maxVal = Math.max(...data.locality_distribution.map(d => d.hospital_count), 1);

    data.locality_distribution.slice(0, 8).forEach(item => {
      const pct = Math.round((item.hospital_count / maxVal) * 100);
      const row = document.createElement("div");
      row.className = "bar-row";
      row.innerHTML = `
        <div class="bar-info">
          <span>${item.locality}</span>
          <span>${item.hospital_count} facilities</span>
        </div>
        <div class="bar-track">
          <div class="bar-fill" style="width: ${pct}%;"></div>
        </div>
      `;
      barsContainer.appendChild(row);
    });

    // Speciality Breakdown Chips
    const specContainer = document.getElementById("specialityTags");
    specContainer.innerHTML = "";
    data.speciality_distribution.forEach(s => {
      const badge = document.createElement("div");
      badge.className = "spec-badge-large";
      badge.innerHTML = `<span>${s.speciality}</span> <strong>${s.count}</strong>`;
      specContainer.appendChild(badge);
    });

    // Gap Insights
    const gapContainer = document.getElementById("gapInsightsList");
    gapContainer.innerHTML = "";
    data.gap_insights.forEach(insight => {
      const box = document.createElement("div");
      box.className = `gap-card-box ${insight.severity}`;
      box.innerHTML = `
        <div class="gap-box-title">${insight.area_category}</div>
        <div class="gap-box-desc">${insight.observation}</div>
        <div style="margin-top: 0.5rem; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; color: #64748b;">
          Assessment: ${insight.status}
        </div>
      `;
      gapContainer.appendChild(box);
    });
  } catch (e) {
    console.error("Failed to load analytics:", e);
  }
}

/* Trigger Overpass Live Sync */
async function triggerOsmSync() {
  const btn = document.getElementById("refreshOsmBtn");
  btn.disabled = true;
  btn.textContent = "Syncing OSM...";

  try {
    const resp = await fetch("/api/refresh-osm", { method: "POST" });
    const json = await resp.json();
    alert(`OSM Sync Status: ${json.message} Total records: ${json.total_records || 'Updated'}`);
    loadAllHospitals();
    loadAnalytics();
  } catch (err) {
    alert("Live OSM sync failed. Ensure internet connectivity is active.");
  } finally {
    btn.disabled = false;
    btn.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="23 4 23 10 17 10"></polyline>
        <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
      </svg> Sync OSM
    `;
  }
}

function updateActiveFilterLabel(text) {
  const el = document.getElementById("activeFilterLabel");
  if (el) el.innerHTML = `Showing: <strong>${text}</strong>`;
}

function showLoader(visible) {
  const loader = document.getElementById("loader");
  if (loader) loader.style.display = visible ? "flex" : "none";
}