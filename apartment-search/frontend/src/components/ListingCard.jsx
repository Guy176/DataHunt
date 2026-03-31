import React from "react";
import { Heart, MapPin, BedDouble, Layers, Ruler, ExternalLink, Trash2 } from "lucide-react";

const SOURCE_LABEL = { yad2: "Yad2", madlan: "Madlan", manual: "Manual" };

export default function ListingCard({ listing, onToggleFav, onDelete }) {
  const {
    id, source, title, price, rooms, floor, size_sqm,
    city, neighborhood, address, image_url, url, is_favorite,
  } = listing;

  const badgeClass = `badge-${source}` ;
  const locationLabel = [neighborhood, city].filter(Boolean).join(", ") || address || "—";

  function fmt(n) {
    if (n == null) return "—";
    return Number(n).toLocaleString("he-IL");
  }

  return (
    <article className="listing-card bg-white rounded-2xl overflow-hidden shadow-sm border border-slate-200 flex flex-col">
      {/* Image */}
      <div className="relative aspect-[4/3] bg-slate-100 overflow-hidden">
        {image_url ? (
          <img
            src={image_url}
            alt={title}
            className="w-full h-full object-cover"
            loading="lazy"
            onError={(e) => { e.target.style.display = "none"; }}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-slate-300">
            <BedDouble size={48} strokeWidth={1} />
          </div>
        )}

        {/* Source badge */}
        <span className={`absolute top-2 left-2 text-xs font-semibold px-2 py-0.5 rounded-full ${badgeClass}`}>
          {SOURCE_LABEL[source] || source}
        </span>

        {/* Favorite btn */}
        <button
          onClick={() => onToggleFav(id)}
          className="absolute top-2 right-2 w-8 h-8 bg-white/80 backdrop-blur rounded-full flex items-center justify-center shadow transition-transform active:scale-90"
          aria-label={is_favorite ? "Remove from saved" : "Save listing"}
        >
          <Heart
            size={16}
            className={is_favorite ? "fill-rose-500 text-rose-500" : "text-slate-400"}
          />
        </button>
      </div>

      {/* Body */}
      <div className="p-3 flex flex-col gap-2 flex-1">
        {/* Price */}
        <div className="flex items-start justify-between gap-2">
          <span className="price-tag text-xl font-bold text-slate-800">
            {price ? `₪${fmt(price)}` : "Price n/a"}
            {price && <span className="text-sm font-normal text-slate-400">/mo</span>}
          </span>
        </div>

        {/* Title */}
        {title && (
          <p className="text-sm text-slate-600 line-clamp-1 rtl-text">{title}</p>
        )}

        {/* Location */}
        <div className="flex items-center gap-1 text-sm text-slate-500">
          <MapPin size={13} className="shrink-0 text-brand-500" />
          <span className="line-clamp-1 rtl-text">{locationLabel}</span>
        </div>

        {/* Stats row */}
        <div className="flex items-center gap-3 text-sm text-slate-600">
          {rooms != null && (
            <Stat icon={<BedDouble size={13} />} label={`${rooms} rooms`} />
          )}
          {floor != null && (
            <Stat icon={<Layers size={13} />} label={`Floor ${floor}`} />
          )}
          {size_sqm != null && (
            <Stat icon={<Ruler size={13} />} label={`${fmt(size_sqm)} m²`} />
          )}
        </div>

        {/* Footer */}
        <div className="mt-auto flex items-center gap-2 pt-1">
          {url ? (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-1 flex items-center justify-center gap-1.5 bg-brand-50 hover:bg-brand-100 text-brand-700 text-sm font-medium py-2 rounded-xl transition-colors"
            >
              View Listing
              <ExternalLink size={13} />
            </a>
          ) : (
            <span className="flex-1 text-center text-xs text-slate-400">No link</span>
          )}
          <button
            onClick={() => onDelete(id)}
            className="w-9 h-9 flex items-center justify-center rounded-xl border border-slate-200 hover:bg-red-50 hover:border-red-200 text-slate-400 hover:text-red-500 transition-colors"
            aria-label="Delete"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>
    </article>
  );
}

function Stat({ icon, label }) {
  return (
    <span className="flex items-center gap-0.5 text-slate-500">
      {icon}
      {label}
    </span>
  );
}
