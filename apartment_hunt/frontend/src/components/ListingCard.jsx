import React, { useState } from "react";

const SOURCE = {
  yad2:   { label: "Yad2",   color: "#FF6B35" },
  madlan: { label: "Madlan", color: "#A855F7" },
  manual: { label: "Manual", color: "#10B981" },
};

function Price({ value }) {
  if (!value) return null;
  const formatted = Number(value).toLocaleString("he-IL");
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="text-2xl font-bold" style={{ fontFamily: "'Fira Code', monospace", color: "var(--accent)" }}>
        ₪{formatted}
      </span>
      <span className="text-xs" style={{ color: "var(--text-muted)" }}>/mo</span>
    </div>
  );
}

function Stat({ icon, value, label }) {
  if (value === null || value === undefined) return null;
  return (
    <div className="flex items-center gap-1 text-xs" style={{ fontFamily: "'Fira Code', monospace", color: "var(--text-dim)" }}>
      <span>{icon}</span>
      <span>{value}</span>
      {label && <span style={{ color: "var(--text-muted)" }}>{label}</span>}
    </div>
  );
}

export default function ListingCard({ listing: l, onFav, onDelete }) {
  const [imgErr, setImgErr] = useState(false);
  const src = SOURCE[l.source] || { label: l.source, color: "#6B7A8D" };
  const loc = [l.neighborhood, l.city].filter(Boolean).join(", ");

  return (
    <article
      className="rounded-2xl overflow-hidden flex flex-col group transition-all duration-300"
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
      }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = "var(--border-hover)";
        e.currentTarget.style.transform   = "translateY(-3px)";
        e.currentTarget.style.boxShadow   = "0 12px 40px rgba(0,0,0,0.4)";
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = "var(--border)";
        e.currentTarget.style.transform   = "translateY(0)";
        e.currentTarget.style.boxShadow   = "none";
      }}>

      {/* Image */}
      <div className="relative overflow-hidden shrink-0" style={{ height: 180, background: "var(--surface-2)" }}>
        {l.image_url && !imgErr
          ? <img src={l.image_url} alt="" onError={() => setImgErr(true)}
              className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105" />
          : (
            <div className="w-full h-full flex items-center justify-center"
              style={{ background: "var(--surface-2)" }}>
              <span className="text-4xl opacity-20">⌂</span>
            </div>
          )
        }

        {/* Gradient overlay */}
        <div className="absolute inset-0" style={{ background: "linear-gradient(to top, rgba(8,12,20,0.7) 0%, transparent 50%)" }} />

        {/* Source badge */}
        <div className="absolute top-3 left-3">
          <span className="text-[10px] font-bold tracking-widest uppercase px-2 py-1 rounded-md"
            style={{ background: `${src.color}22`, color: src.color, border: `1px solid ${src.color}44` }}>
            {src.label}
          </span>
        </div>

        {/* Fav */}
        <button onClick={() => onFav(l.id)}
          className="absolute top-2.5 right-2.5 w-7 h-7 rounded-full flex items-center justify-center text-base transition-all"
          style={{ background: "rgba(8,12,20,0.6)", backdropFilter: "blur(4px)" }}>
          {l.is_favorite ? "❤️" : "🤍"}
        </button>
      </div>

      {/* Body */}
      <div className="p-4 flex flex-col flex-1 gap-2">
        <Price value={l.price} />

        <div>
          <p className="text-sm font-semibold leading-snug line-clamp-2" style={{ color: "var(--text)" }}>
            {l.title || l.address || "Untitled listing"}
          </p>
          {loc && (
            <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
              📍 {loc}
            </p>
          )}
        </div>

        {/* Stats row */}
        <div className="flex flex-wrap gap-3 py-2"
          style={{ borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)" }}>
          <Stat icon="🛏" value={l.rooms}    label="rm" />
          <Stat icon="🏢" value={l.floor !== null && l.floor !== undefined ? `${l.floor}F` : null} />
          <Stat icon="📐" value={l.size_sqm} label="m²" />
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 mt-auto pt-1">
          {l.url
            ? <a href={l.url} target="_blank" rel="noreferrer"
                className="flex-1 text-center text-xs font-bold tracking-widest uppercase py-2 rounded-lg transition-all"
                style={{ background: "var(--accent-dim)", color: "var(--accent)", border: "1px solid var(--accent-glow)" }}
                onMouseEnter={e => e.currentTarget.style.background = "var(--accent-glow)"}
                onMouseLeave={e => e.currentTarget.style.background = "var(--accent-dim)"}>
                VIEW ↗
              </a>
            : <div className="flex-1" />
          }
          <button onClick={() => onDelete(l.id)}
            className="w-8 h-8 flex items-center justify-center rounded-lg text-sm transition-all"
            style={{ color: "var(--text-muted)", border: "1px solid var(--border)" }}
            onMouseEnter={e => { e.currentTarget.style.color = "var(--red)"; e.currentTarget.style.borderColor = "var(--red)"; }}
            onMouseLeave={e => { e.currentTarget.style.color = "var(--text-muted)"; e.currentTarget.style.borderColor = "var(--border)"; }}>
            ✕
          </button>
        </div>
      </div>
    </article>
  );
}
