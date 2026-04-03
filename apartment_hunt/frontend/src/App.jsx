import React, { useState, useEffect, useRef } from "react";
import { api } from "./api";
import Filters from "./components/Filters";
import ListingGrid from "./components/ListingGrid";

const DEFAULTS = {
  city: "", neighborhood: "", min_price: "", max_price: "",
  min_rooms: "", max_rooms: "", min_floor: "", max_floor: "",
  sources: ["yad2", "madlan"], sort_by: "scraped_at", sort_order: "desc",
};

export default function App() {
  const [tab,       setTab]       = useState("search");
  const [filters,   setFilters]   = useState(DEFAULTS);
  const [listings,  setListings]  = useState([]);
  const [loading,   setLoading]   = useState(false);
  const [scanning,  setScanning]  = useState(false);
  const [toast,     setToast]     = useState("");
  const pollRef = useRef(null);

  useEffect(() => { load(); }, [tab]); // eslint-disable-line

  async function load(f = filters) {
    setLoading(true);
    try {
      const params = {
        city:          f.city          || undefined,
        neighborhood:  f.neighborhood  || undefined,
        min_price:     f.min_price     || undefined,
        max_price:     f.max_price     || undefined,
        min_rooms:     f.min_rooms     || undefined,
        max_rooms:     f.max_rooms     || undefined,
        min_floor:     f.min_floor     || undefined,
        max_floor:     f.max_floor     || undefined,
        source:        f.sources.length === 1 ? f.sources[0] : undefined,
        sort_by:       f.sort_by,
        sort_order:    f.sort_order,
        favorites_only: tab === "favorites" || undefined,
        limit: 200,
      };
      const data = await api.getListings(params);
      setListings(Array.isArray(data) ? data : []);
    } catch (e) {
      showToast("Failed to load listings");
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  async function scan() {
    if (scanning) return;
    setScanning(true);
    showToast("Starting scan…");
    try {
      const body = {
        city:         filters.city         || undefined,
        neighborhood: filters.neighborhood || undefined,
        min_price:    filters.min_price    ? Number(filters.min_price)    : undefined,
        max_price:    filters.max_price    ? Number(filters.max_price)    : undefined,
        min_rooms:    filters.min_rooms    ? Number(filters.min_rooms)    : undefined,
        max_rooms:    filters.max_rooms    ? Number(filters.max_rooms)    : undefined,
        sources:      filters.sources,
      };
      const { job_id } = await api.startScrape(body);
      let attempts = 0;
      pollRef.current = setInterval(async () => {
        attempts++;
        try {
          const s = await api.getStatus(job_id);
          if (s.status === "done") {
            clearInterval(pollRef.current);
            setScanning(false);
            showToast(`Found ${s.count} listings`);
            load();
          } else if (s.status === "running") {
            showToast("Scanning…");
          }
          if (attempts > 120) {
            clearInterval(pollRef.current);
            setScanning(false);
            showToast("Scan timed out");
          }
        } catch {
          clearInterval(pollRef.current);
          setScanning(false);
        }
      }, 2000);
    } catch (e) {
      setScanning(false);
      showToast("Scan failed — check backend");
      console.error(e);
    }
  }

  function showToast(msg) {
    setToast(msg);
    setTimeout(() => setToast(""), 5000);
  }

  async function toggleFav(id) {
    try {
      const { is_favorite } = await api.toggleFavorite(id);
      setListings(prev => prev.map(l => l.id === id ? { ...l, is_favorite } : l));
    } catch (e) { console.error(e); }
  }

  async function del(id) {
    if (!confirm("Remove listing?")) return;
    try {
      await api.deleteListing(id);
      setListings(prev => prev.filter(l => l.id !== id));
    } catch (e) { console.error(e); }
  }

  useEffect(() => () => clearInterval(pollRef.current), []);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b shadow-sm sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between gap-4">
          <span className="font-bold text-lg text-blue-600">🏠 Apartment Hunt</span>
          <nav className="flex gap-1">
            {["search", "favorites"].map(t => (
              <button key={t} onClick={() => setTab(t)}
                className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors
                  ${tab === t ? "bg-blue-600 text-white" : "text-gray-600 hover:bg-gray-100"}`}>
                {t === "search" ? "Search" : "Saved"}
              </button>
            ))}
          </nav>
          <button onClick={scan} disabled={scanning}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50
              text-white text-sm font-medium px-4 py-2 rounded-full transition-colors">
            {scanning
              ? <><span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"/>Scanning…</>
              : "⚡ Scan Now"}
          </button>
        </div>
      </header>

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50
          bg-gray-900 text-white text-sm px-5 py-2.5 rounded-full shadow-lg">
          {toast}
        </div>
      )}

      <main className="max-w-7xl mx-auto px-4 py-4">
        <div className="lg:grid lg:grid-cols-[300px_1fr] lg:gap-6">
          <aside className="mb-4 lg:mb-0">
            <Filters
              filters={filters}
              onChange={setFilters}
              onSearch={() => load()}
              loading={loading}
            />
            <p className="text-xs text-gray-400 text-center mt-2">
              {listings.length} listing{listings.length !== 1 ? "s" : ""} shown
            </p>
          </aside>
          <div>
            {tab === "favorites" && (
              <p className="text-sm text-gray-500 mb-3 font-medium">Saved listings</p>
            )}
            <ListingGrid listings={listings} loading={loading} onFav={toggleFav} onDelete={del} />
          </div>
        </div>
      </main>
    </div>
  );
}
