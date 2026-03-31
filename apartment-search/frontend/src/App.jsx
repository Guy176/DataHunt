import React, { useState, useEffect, useCallback, useRef } from "react";
import Header from "./components/Header";
import SearchFilters from "./components/SearchFilters";
import ListingGrid from "./components/ListingGrid";
import AddManualListing from "./components/AddManualListing";
import {
  fetchListings, toggleFavorite, deleteListing,
  startScrape, pollScrapeStatus,
} from "./services/api";

const DEFAULT_FILTERS = {
  min_price: "", max_price: "",
  min_rooms: "", max_rooms: "",
  min_floor: "", max_floor: "",
  city: "", neighborhood: "",
  sources: ["yad2", "madlan"],
  sort_by: "scraped_at",
  sort_order: "desc",
};

export default function App() {
  const [tab, setTab] = useState("search");
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [listings, setListings] = useState([]);
  const [loading, setLoading] = useState(false);
  const [scraping, setScraping] = useState(false);
  const [scrapeMsg, setScrapeMsg] = useState("");
  const [totalCount, setTotalCount] = useState(null);
  const pollRef = useRef(null);

  // Load listings on mount and when tab changes back to search
  useEffect(() => {
    if (tab === "search" || tab === "favorites") {
      loadListings();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const loadListings = useCallback(async (overrideFilters) => {
    setLoading(true);
    const f = overrideFilters || filters;
    try {
      const params = buildApiParams(f, tab === "favorites");
      const data = await fetchListings(params);
      setListings(data);
      setTotalCount(data.length);
    } catch (err) {
      console.error("fetchListings error", err);
    } finally {
      setLoading(false);
    }
  }, [filters, tab]);

  function buildApiParams(f, favoritesOnly = false) {
    return {
      min_price: f.min_price || undefined,
      max_price: f.max_price || undefined,
      min_rooms: f.min_rooms || undefined,
      max_rooms: f.max_rooms || undefined,
      min_floor: f.min_floor || undefined,
      max_floor: f.max_floor || undefined,
      city: f.city || undefined,
      neighborhood: f.neighborhood || undefined,
      source: f.sources.length === 1 ? f.sources[0] : undefined,
      sort_by: f.sort_by,
      sort_order: f.sort_order,
      favorites_only: favoritesOnly || undefined,
      limit: 200,
    };
  }

  async function handleScrape() {
    if (scraping) return;
    setScraping(true);
    setScrapeMsg("Starting scan…");
    try {
      const scrapeFilters = {
        min_price: filters.min_price ? Number(filters.min_price) : undefined,
        max_price: filters.max_price ? Number(filters.max_price) : undefined,
        min_rooms: filters.min_rooms ? Number(filters.min_rooms) : undefined,
        max_rooms: filters.max_rooms ? Number(filters.max_rooms) : undefined,
        min_floor: filters.min_floor ? Number(filters.min_floor) : undefined,
        max_floor: filters.max_floor ? Number(filters.max_floor) : undefined,
        city: filters.city || undefined,
        neighborhood: filters.neighborhood || undefined,
        sources: filters.sources,
      };
      const { job_id } = await startScrape(scrapeFilters);

      // Poll until done
      let attempts = 0;
      pollRef.current = setInterval(async () => {
        attempts++;
        try {
          const status = await pollScrapeStatus(job_id);
          if (status.status === "done") {
            clearInterval(pollRef.current);
            setScraping(false);
            setScrapeMsg(`Found ${status.count} listings`);
            await loadListings();
            setTimeout(() => setScrapeMsg(""), 4000);
          } else if (status.status === "running") {
            setScrapeMsg("Scanning sites…");
          }
          if (attempts > 120) {
            clearInterval(pollRef.current);
            setScraping(false);
            setScrapeMsg("Scan timed out");
          }
        } catch {
          clearInterval(pollRef.current);
          setScraping(false);
        }
      }, 2000);
    } catch (err) {
      setScraping(false);
      setScrapeMsg("Scan failed");
      console.error(err);
    }
  }

  async function handleToggleFav(id) {
    try {
      const { is_favorite } = await toggleFavorite(id);
      setListings((prev) =>
        prev.map((l) => (l.id === id ? { ...l, is_favorite } : l))
      );
    } catch (err) {
      console.error(err);
    }
  }

  async function handleDelete(id) {
    if (!confirm("Remove this listing?")) return;
    try {
      await deleteListing(id);
      setListings((prev) => prev.filter((l) => l.id !== id));
    } catch (err) {
      console.error(err);
    }
  }

  // Cleanup poll on unmount
  useEffect(() => () => clearInterval(pollRef.current), []);

  return (
    <div className="min-h-screen bg-slate-50">
      <Header
        tab={tab}
        setTab={setTab}
        scraping={scraping}
        onScrape={handleScrape}
      />

      {/* Scrape status toast */}
      {scrapeMsg && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 bg-slate-800 text-white text-sm px-4 py-2 rounded-full shadow-lg animate-bounce-once">
          {scrapeMsg}
        </div>
      )}

      <main className="max-w-7xl mx-auto px-4 py-4">
        {/* Search Tab */}
        {(tab === "search" || tab === "favorites") && (
          <div className="lg:grid lg:grid-cols-[280px_1fr] lg:gap-6">
            {/* Sidebar filters */}
            <aside className="filter-sidebar mb-4 lg:mb-0">
              <SearchFilters
                filters={filters}
                onChange={setFilters}
                onSearch={() => loadListings()}
                loading={loading}
              />
              {totalCount !== null && (
                <p className="text-xs text-slate-400 text-center mt-3">
                  {totalCount} listing{totalCount !== 1 ? "s" : ""} shown
                </p>
              )}
            </aside>

            {/* Results */}
            <div>
              {tab === "favorites" && (
                <div className="mb-4 flex items-center gap-2">
                  <span className="text-sm font-medium text-slate-600">
                    Showing saved listings
                  </span>
                </div>
              )}
              <ListingGrid
                listings={listings}
                loading={loading}
                onToggleFav={handleToggleFav}
                onDelete={handleDelete}
              />
            </div>
          </div>
        )}

        {/* Add Manual Tab */}
        {tab === "add" && (
          <AddManualListing onAdded={() => { setTab("search"); loadListings(); }} />
        )}
      </main>
    </div>
  );
}
