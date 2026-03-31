import axios from "axios";

const BASE = import.meta.env.VITE_API_URL || "/api";

const api = axios.create({ baseURL: BASE, timeout: 30000 });

// ── Listings ──────────────────────────────────────────────────────────────────

export async function fetchListings(filters = {}) {
  const { data } = await api.get("/listings/", { params: cleanParams(filters) });
  return data;
}

export async function countListings(params = {}) {
  const { data } = await api.get("/listings/count", { params: cleanParams(params) });
  return data.count;
}

export async function toggleFavorite(id) {
  const { data } = await api.patch(`/listings/${id}/favorite`);
  return data;
}

export async function addManualListing(listing) {
  const { data } = await api.post("/listings/manual", listing);
  return data;
}

export async function deleteListing(id) {
  await api.delete(`/listings/${id}`);
}

// ── Scraping ──────────────────────────────────────────────────────────────────

export async function startScrape(filters = {}) {
  const { data } = await api.post("/scrape/start", filters);
  return data; // { job_id, status }
}

export async function pollScrapeStatus(jobId) {
  const { data } = await api.get(`/scrape/status/${jobId}`);
  return data; // { job_id, status, count }
}

export async function getSources() {
  const { data } = await api.get("/scrape/sources");
  return data.sources;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function cleanParams(obj) {
  return Object.fromEntries(
    Object.entries(obj).filter(([, v]) => v !== null && v !== undefined && v !== "")
  );
}
