import React from "react";
import ListingCard from "./ListingCard";

export default function ListingGrid({ listings, loading, onFav, onDelete }) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="rounded-2xl overflow-hidden skeleton" style={{ height: 340 }} />
        ))}
      </div>
    );
  }

  if (!listings.length) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <div className="text-6xl mb-5 opacity-20">⌂</div>
        <p className="text-sm font-semibold tracking-widest uppercase mb-2" style={{ color: "var(--text-muted)" }}>
          No listings found
        </p>
        <p className="text-xs" style={{ color: "var(--text-muted)", maxWidth: 240 }}>
          Press{" "}
          <span className="font-bold" style={{ color: "var(--accent)" }}>⚡ SCAN NOW</span>
          {" "}to fetch fresh listings from Yad2 and Madlan
        </p>
        <div className="mt-6 flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs"
          style={{ color: "var(--text-muted)", fontFamily: "'Fira Code', monospace", background: "var(--surface)", border: "1px solid var(--border)" }}>
          <span style={{ color: "var(--accent)" }}>$</span> awaiting scan…
          <span className="animate-pulse">_</span>
        </div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
      {listings.map((l, i) => (
        <div key={l.id} className="card-enter" style={{ animationDelay: `${Math.min(i * 40, 400)}ms` }}>
          <ListingCard listing={l} onFav={onFav} onDelete={onDelete} />
        </div>
      ))}
    </div>
  );
}
