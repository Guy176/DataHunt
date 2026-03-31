import React from "react";
import ListingCard from "./ListingCard";
import { SearchX } from "lucide-react";

export default function ListingGrid({ listings, loading, onToggleFav, onDelete }) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    );
  }

  if (!listings.length) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-slate-400 gap-4">
        <SearchX size={56} strokeWidth={1} />
        <p className="text-lg font-medium">No listings found</p>
        <p className="text-sm">Try adjusting your filters or click <strong>Scan Now</strong>.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
      {listings.map((l) => (
        <ListingCard
          key={l.id}
          listing={l}
          onToggleFav={onToggleFav}
          onDelete={onDelete}
        />
      ))}
    </div>
  );
}

function SkeletonCard() {
  return (
    <div className="bg-white rounded-2xl overflow-hidden border border-slate-200 shadow-sm">
      <div className="skeleton aspect-[4/3]" />
      <div className="p-3 space-y-2">
        <div className="skeleton h-6 w-24 rounded" />
        <div className="skeleton h-4 w-40 rounded" />
        <div className="skeleton h-4 w-32 rounded" />
        <div className="skeleton h-9 w-full rounded-xl mt-2" />
      </div>
    </div>
  );
}
