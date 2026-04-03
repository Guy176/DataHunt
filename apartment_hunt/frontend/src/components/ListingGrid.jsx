import React from "react";
import ListingCard from "./ListingCard";

export default function ListingGrid({ listings, loading, onFav, onDelete }) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="bg-white rounded-xl border animate-pulse h-72" />
        ))}
      </div>
    );
  }

  if (!listings.length) {
    return (
      <div className="text-center py-20 text-gray-400">
        <div className="text-5xl mb-3">🏠</div>
        <p className="font-medium">No listings yet</p>
        <p className="text-sm mt-1">Click <strong>Scan Now</strong> to fetch listings from Yad2 & Madlan</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
      {listings.map(l => (
        <ListingCard key={l.id} listing={l} onFav={onFav} onDelete={onDelete} />
      ))}
    </div>
  );
}
