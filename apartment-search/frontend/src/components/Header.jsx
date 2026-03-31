import React from "react";
import { Home, Heart, PlusCircle, RefreshCw } from "lucide-react";

export default function Header({ tab, setTab, scraping, onScrape }) {
  return (
    <header className="sticky top-0 z-40 bg-white border-b border-slate-200 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
        {/* Logo */}
        <div className="flex items-center gap-2 font-bold text-brand-600 text-lg select-none">
          <Home size={22} strokeWidth={2.5} />
          <span className="hidden sm:inline">ApartSearch IL</span>
          <span className="sm:hidden">ApartSearch</span>
        </div>

        {/* Nav tabs */}
        <nav className="flex items-center gap-1">
          <NavBtn active={tab === "search"} onClick={() => setTab("search")}>
            Search
          </NavBtn>
          <NavBtn active={tab === "favorites"} onClick={() => setTab("favorites")}>
            <Heart size={14} className="inline mr-1" />
            Saved
          </NavBtn>
          <NavBtn active={tab === "add"} onClick={() => setTab("add")}>
            <PlusCircle size={14} className="inline mr-1" />
            Add
          </NavBtn>
        </nav>

        {/* Scrape button */}
        <button
          onClick={onScrape}
          disabled={scraping}
          title="Fetch latest listings from Yad2 & Madlan"
          className="flex items-center gap-1.5 bg-brand-600 hover:bg-brand-700 disabled:opacity-60 text-white text-sm font-medium px-3 py-1.5 rounded-lg transition-colors"
        >
          <RefreshCw size={14} className={scraping ? "animate-spin" : ""} />
          <span className="hidden sm:inline">{scraping ? "Scanning…" : "Scan Now"}</span>
        </button>
      </div>
    </header>
  );
}

function NavBtn({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
        active
          ? "bg-brand-100 text-brand-700"
          : "text-slate-600 hover:bg-slate-100"
      }`}
    >
      {children}
    </button>
  );
}
