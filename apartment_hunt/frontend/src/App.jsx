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
  const [tab,      setTab]      = useState("search");
  const [filters,  setFilters]  = useState(DEFAULTS);
  const [listings, setListings] = useState([]);
  const [loading,  setLoading]  = useState(false);
  const [scanning, setScanning] = useState(false);
  const [toast,    setToast]    = useState(null);
  const [scanCount, setScanCount] = useState(null);
  const pollRef = useRef(null);

  useEffect(() => { load(); }, [tab]); // eslint-disable-line

  async function load(f = filters) {
    setLoading(true);
    try {
      const data = await api.getListings({
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
      });
      setListings(Array.isArray(data) ? data : []);
    } catch (e) {
      toast("Error loading listings", "error");
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  async function scan() {
    if (scanning) return;
    setScanning(true);
    setScanCount(null);
    showToast("Initialising scan…", "info");
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
            setScanCount(s.count);
            showToast(`${s.count} listings found`, "success");
            load();
          } else if (s.status === "running") {
            showToast("Scraping Yad2 & Madlan…", "info");
          }
          if (attempts > 120) {
            clearInterval(pollRef.current);
            setScanning(false);
            showToast("Scan timed out", "error");
          }
        } catch {
          clearInterval(pollRef.current);
          setScanning(false);
        }
      }, 2000);
    } catch (e) {
      setScanning(false);
      showToast("Scan failed — is the backend running?", "error");
      console.error(e);
    }
  }

  function showToast(msg, type = "info") {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 5000);
  }

  async function toggleFav(id) {
    try {
      const { is_favorite } = await api.toggleFavorite(id);
      setListings(prev => prev.map(l => l.id === id ? { ...l, is_favorite } : l));
    } catch (e) { console.error(e); }
  }

  async function del(id) {
    if (!confirm("Remove this listing?")) return;
    try {
      await api.deleteListing(id);
      setListings(prev => prev.filter(l => l.id !== id));
    } catch (e) { console.error(e); }
  }

  useEffect(() => () => clearInterval(pollRef.current), []);

  const toastColors = {
    info:    "border-[var(--accent)] text-[var(--accent)]",
    success: "border-emerald-400 text-emerald-400",
    error:   "border-[var(--red)] text-[var(--red)]",
  };

  return (
    <div className="min-h-screen" style={{ background: "var(--bg)" }}>
      {/* ── HEADER ── */}
      <header style={{ background: "var(--surface)", borderBottom: "1px solid var(--border)" }}
        className="sticky top-0 z-40 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-4">

          {/* Logo */}
          <div className="flex items-center gap-3 shrink-0">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center text-base"
              style={{ background: "var(--accent-dim)", border: "1px solid var(--accent-glow)" }}>
              🏠
            </div>
            <div>
              <div className="font-bold text-sm tracking-wide" style={{ color: "var(--text)" }}>
                APARTMENT HUNT
              </div>
              <div className="text-[10px] tracking-widest" style={{ color: "var(--text-muted)" }}>
                ISRAEL RENTAL SEARCH
              </div>
            </div>
          </div>

          {/* Tabs */}
          <nav className="flex gap-1 p-1 rounded-xl" style={{ background: "var(--surface-2)" }}>
            {[
              { id: "search",    label: "Search"  },
              { id: "favorites", label: "Saved"   },
            ].map(t => (
              <button key={t.id} onClick={() => setTab(t.id)}
                className="px-4 py-1.5 rounded-lg text-xs font-semibold tracking-wider uppercase transition-all"
                style={tab === t.id
                  ? { background: "var(--accent)", color: "#080C14" }
                  : { color: "var(--text-muted)" }}>
                {t.label}
              </button>
            ))}
          </nav>

          {/* Scan button */}
          <button onClick={scan} disabled={scanning}
            className="flex items-center gap-2 px-5 py-2 rounded-xl text-xs font-bold tracking-widest uppercase transition-all disabled:opacity-60 shrink-0"
            style={{
              background: scanning ? "var(--accent-dim)" : "var(--accent)",
              color: scanning ? "var(--accent)" : "#080C14",
              border: scanning ? "1px solid var(--accent)" : "none",
              animation: scanning ? "scanPulse 1.5s ease-in-out infinite" : "none",
            }}>
            {scanning ? (
              <>
                <span className="w-3 h-3 rounded-full border-2 animate-spin"
                  style={{ borderColor: "var(--accent) transparent transparent transparent" }} />
                SCANNING
              </>
            ) : (
              <>⚡ SCAN NOW</>
            )}
          </button>
        </div>
      </header>

      {/* ── TOAST ── */}
      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 px-5 py-3 rounded-xl text-sm font-medium tracking-wide"
          style={{ background: "var(--surface)", border: `1px solid`, backdropFilter: "blur(12px)" }}
          onClick={() => setToast(null)}>
          <span className={toastColors[toast.type]}>{toast.msg}</span>
        </div>
      )}

      {/* ── SCAN TICKER ── */}
      {scanning && (
        <div className="h-0.5 w-full overflow-hidden" style={{ background: "var(--surface-2)" }}>
          <div className="h-full animate-pulse" style={{ background: "var(--accent)", width: "60%" }} />
        </div>
      )}

      {/* ── MAIN ── */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        <div className="lg:grid lg:grid-cols-[280px_1fr] lg:gap-6">

          {/* Sidebar */}
          <aside className="mb-6 lg:mb-0">
            <Filters filters={filters} onChange={setFilters} onSearch={() => load()} loading={loading} />

            {/* Stats bar */}
            <div className="mt-3 flex items-center justify-between px-1">
              <span className="text-xs" style={{ color: "var(--text-muted)", fontFamily: "'Fira Code', monospace" }}>
                {listings.length} results
              </span>
              {scanCount !== null && (
                <span className="text-xs" style={{ color: "var(--accent)", fontFamily: "'Fira Code', monospace" }}>
                  +{scanCount} from last scan
                </span>
              )}
            </div>
          </aside>

          {/* Grid */}
          <section>
            {tab === "favorites" && (
              <div className="mb-4 flex items-center gap-2">
                <div className="w-2 h-2 rounded-full" style={{ background: "var(--accent)" }} />
                <span className="text-xs tracking-widest uppercase" style={{ color: "var(--text-muted)" }}>
                  Saved listings
                </span>
              </div>
            )}
            <ListingGrid listings={listings} loading={loading} onFav={toggleFav} onDelete={del} />
          </section>
        </div>
      </main>
    </div>
  );
}
