import React from "react";

function fmt(n) {
  if (!n) return null;
  return "₪" + Number(n).toLocaleString("he-IL");
}

const SOURCE_COLOR = {
  yad2:   "bg-orange-100 text-orange-700",
  madlan: "bg-purple-100 text-purple-700",
  manual: "bg-green-100  text-green-700",
};

export default function ListingCard({ listing: l, onFav, onDelete }) {
  const price = fmt(l.price);
  const loc   = [l.neighborhood, l.city].filter(Boolean).join(", ");

  return (
    <div className="bg-white rounded-xl border shadow-sm overflow-hidden flex flex-col hover:shadow-md transition-shadow">
      {/* Image */}
      <div className="relative h-44 bg-gray-100 flex items-center justify-center shrink-0">
        {l.image_url
          ? <img src={l.image_url} alt="" className="w-full h-full object-cover"
              onError={e => { e.target.style.display = "none"; }} />
          : <span className="text-4xl">🛏️</span>}
        <span className={`absolute top-2 left-2 text-xs font-semibold px-2 py-0.5 rounded-full ${SOURCE_COLOR[l.source] || "bg-gray-100 text-gray-600"}`}>
          {l.source}
        </span>
        <button onClick={() => onFav(l.id)}
          className="absolute top-2 right-2 text-xl leading-none drop-shadow">
          {l.is_favorite ? "❤️" : "🤍"}
        </button>
      </div>

      {/* Body */}
      <div className="p-3 flex flex-col flex-1">
        {price && <p className="text-xl font-bold text-blue-600">{price}<span className="text-sm font-normal text-gray-400">/mo</span></p>}
        <p className="font-semibold text-gray-800 text-sm mt-0.5 line-clamp-2">{l.title || l.address || "—"}</p>
        {loc && <p className="text-xs text-gray-500 mt-0.5">{loc}</p>}

        {/* Stats */}
        <div className="flex gap-3 mt-2 text-xs text-gray-600">
          {l.rooms    && <span>🛏 {l.rooms} rooms</span>}
          {l.floor !== null && l.floor !== undefined && <span>🏢 Floor {l.floor}</span>}
          {l.size_sqm && <span>📐 {l.size_sqm} m²</span>}
        </div>

        {/* Actions */}
        <div className="flex gap-2 mt-auto pt-3">
          {l.url && (
            <a href={l.url} target="_blank" rel="noreferrer"
              className="flex-1 text-center text-xs font-semibold bg-blue-600 hover:bg-blue-700
                text-white py-1.5 rounded-lg transition-colors">
              View listing ↗
            </a>
          )}
          <button onClick={() => onDelete(l.id)}
            className="text-xs text-gray-400 hover:text-red-500 px-2 transition-colors">
            🗑
          </button>
        </div>
      </div>
    </div>
  );
}
