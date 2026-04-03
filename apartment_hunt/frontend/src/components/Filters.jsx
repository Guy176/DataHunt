import React, { useState } from "react";

const CITIES = [
  "תל אביב","ירושלים","חיפה","ראשון לציון","פתח תקווה","אשדוד","נתניה",
  "באר שבע","בני ברק","חולון","רמת גן","אשקלון","רחובות","בת ים",
  "כפר סבא","הרצליה","חדרה","מודיעין","לוד","אילת","גבעתיים","בית שמש",
];

const NEIGHBORHOODS = {
  "תל אביב": ["רובע 1 - יפו","רובע 2 - עג'מי ונווה צדק","רובע 3 - לב העיר","רובע 4 - שכונות הצפון הישן","רובע 5 - לב תל אביב","רובע 6 - הצפון הישן","רובע 7 - רמת אביב","רובע 8 - אוניברסיטה","רובע 9 - הצפון החדש","פלורנטין","נווה שאנן","שפירא","מונטיפיורי","כרם התימנים"],
  "ירושלים": ["רחביה","טלביה","בקעה","קטמון","גילה","הר חומה","פסגת זאב","רמות אלון","מעלות דפנה","נווה יעקב","גבעת שאול","קריית יובל","בית וגן","ניות","מחנה יהודה","גבעת משואה","ציר יפו","מרכז העיר"],
  "חיפה": ["כרמל מרכזי","כרמל צרפתי","כרמל מצפה","אחוזה","נווה שאנן","רמות רמז","קריית חיים מערבית","קריית חיים מזרחית","קריית שמואל","הדר הכרמל","מרכז הכרמל","נאות פרס","שכונת גורן","בת גלים","הלב"],
  "ראשון לציון": ["נחלת יהודה","ניר צבי","משמרת","רמת אליהו","ורדיה","כרם התימנים"],
  "פתח תקווה": ["כפר גנים","שכונת התקווה","אם המושבות","קריית ספיר","שכונת ז"],
  "רמת גן": ["הבורסה","הביל\"ויים","הגפן ונחלת גנים","הלל","הראשונים","ותיקים","חרוזים","יד לבנים נגבה ותל יהודה","לב העיר","נווה יהושע","ציר זבוטינסקי","קרית בורוכוב","רמת אפעל","רמת חן","רמת עמידר","רמת שקמה","שיכון מזרחי","תל בנימין","תל גנים"],
  "נתניה": ["גבעת השלושה","אגמים","עיר ימים","שכונת נורדאו","פולג","ניצנים","עמידר","קריית נורדאו","שכונה ד"],
  "באר שבע": ["רמות","דלתא","הנגב","גמלים","ט","נווה זאב","עומר","להבים","כרמים"],
  "הרצליה": ["הרצליה פיתוח","הרצליה ב","ניר זוי","שכונת ים"],
};

const ROOMS = ["1","1.5","2","2.5","3","3.5","4","4.5","5","5.5","6+"];
const SORTS = [
  { v: "scraped_at", l: "Newest" },
  { v: "price",      l: "Price"  },
  { v: "rooms",      l: "Rooms"  },
  { v: "floor",      l: "Floor"  },
  { v: "size_sqm",   l: "Size"   },
];

export default function Filters({ filters, onChange, onSearch, loading }) {
  const [open, setOpen] = useState(false);

  function set(key, val) {
    onChange(prev => {
      const next = { ...prev, [key]: val };
      if (key === "city") next.neighborhood = "";
      return next;
    });
  }

  function toggleSource(src) {
    onChange(prev => {
      const s = prev.sources.includes(src)
        ? prev.sources.filter(x => x !== src)
        : [...prev.sources, src];
      return { ...prev, sources: s.length ? s : prev.sources };
    });
  }

  const nbhds = NEIGHBORHOODS[filters.city] || [];
  const hasFilters = filters.city || filters.min_price || filters.max_price ||
    filters.min_rooms || filters.max_rooms;

  const body = (
    <div className="space-y-4 p-4">
      {/* City */}
      <div>
        <label className="block text-xs font-semibold text-gray-500 mb-1">City</label>
        <select value={filters.city} onChange={e => set("city", e.target.value)}
          className="w-full border rounded-lg px-3 py-2 text-sm bg-white">
          <option value="">All cities</option>
          {CITIES.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>

      {/* Neighborhood */}
      <div>
        <label className="block text-xs font-semibold text-gray-500 mb-1">Neighborhood</label>
        <select value={filters.neighborhood} onChange={e => set("neighborhood", e.target.value)}
          className="w-full border rounded-lg px-3 py-2 text-sm bg-white"
          disabled={!nbhds.length}>
          <option value="">All neighborhoods</option>
          {nbhds.map(n => <option key={n} value={n}>{n}</option>)}
        </select>
      </div>

      {/* Price */}
      <div>
        <label className="block text-xs font-semibold text-gray-500 mb-1">Price (₪/month)</label>
        <div className="flex gap-2">
          <input type="number" placeholder="Min" value={filters.min_price}
            onChange={e => set("min_price", e.target.value)}
            className="w-1/2 border rounded-lg px-3 py-2 text-sm" />
          <input type="number" placeholder="Max" value={filters.max_price}
            onChange={e => set("max_price", e.target.value)}
            className="w-1/2 border rounded-lg px-3 py-2 text-sm" />
        </div>
      </div>

      {/* Rooms */}
      <div>
        <label className="block text-xs font-semibold text-gray-500 mb-1">Rooms</label>
        <div className="flex gap-2">
          <select value={filters.min_rooms} onChange={e => set("min_rooms", e.target.value)}
            className="w-1/2 border rounded-lg px-3 py-2 text-sm bg-white">
            <option value="">Min</option>
            {ROOMS.map(r => <option key={r} value={r.replace("+","")}>{r}</option>)}
          </select>
          <select value={filters.max_rooms} onChange={e => set("max_rooms", e.target.value)}
            className="w-1/2 border rounded-lg px-3 py-2 text-sm bg-white">
            <option value="">Max</option>
            {ROOMS.map(r => <option key={r} value={r.replace("+","")}>{r}</option>)}
          </select>
        </div>
      </div>

      {/* Floor */}
      <div>
        <label className="block text-xs font-semibold text-gray-500 mb-1">Floor</label>
        <div className="flex gap-2">
          <input type="number" placeholder="Min" value={filters.min_floor}
            onChange={e => set("min_floor", e.target.value)}
            className="w-1/2 border rounded-lg px-3 py-2 text-sm" />
          <input type="number" placeholder="Max" value={filters.max_floor}
            onChange={e => set("max_floor", e.target.value)}
            className="w-1/2 border rounded-lg px-3 py-2 text-sm" />
        </div>
      </div>

      {/* Sources */}
      <div>
        <label className="block text-xs font-semibold text-gray-500 mb-1">Sources</label>
        <div className="flex gap-3">
          {["yad2","madlan"].map(src => (
            <label key={src} className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={filters.sources.includes(src)}
                onChange={() => toggleSource(src)}
                className="rounded" />
              {src === "yad2" ? "Yad2" : "Madlan"}
            </label>
          ))}
        </div>
      </div>

      {/* Sort */}
      <div>
        <label className="block text-xs font-semibold text-gray-500 mb-1">Sort</label>
        <div className="flex gap-2">
          <select value={filters.sort_by} onChange={e => set("sort_by", e.target.value)}
            className="flex-1 border rounded-lg px-3 py-2 text-sm bg-white">
            {SORTS.map(s => <option key={s.v} value={s.v}>{s.l}</option>)}
          </select>
          <select value={filters.sort_order} onChange={e => set("sort_order", e.target.value)}
            className="w-24 border rounded-lg px-3 py-2 text-sm bg-white">
            <option value="desc">↓ Desc</option>
            <option value="asc">↑ Asc</option>
          </select>
        </div>
      </div>

      {/* Buttons */}
      <div className="flex gap-2 pt-1">
        <button onClick={onSearch} disabled={loading}
          className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50
            text-white font-semibold py-2 rounded-lg text-sm transition-colors">
          {loading ? "Loading…" : "Search"}
        </button>
        {hasFilters && (
          <button onClick={() => { onChange(DEFAULTS); setTimeout(onSearch, 0); }}
            className="px-4 py-2 border rounded-lg text-sm text-gray-600 hover:bg-gray-50">
            Reset
          </button>
        )}
      </div>
    </div>
  );

  return (
    <div className="bg-white rounded-xl border shadow-sm">
      {/* Mobile toggle */}
      <button onClick={() => setOpen(o => !o)}
        className="lg:hidden w-full flex items-center justify-between px-4 py-3 text-sm font-semibold text-gray-700">
        <span>Filters {hasFilters ? "🔵" : ""}</span>
        <span>{open ? "▲" : "▼"}</span>
      </button>
      <div className={`lg:block ${open ? "block" : "hidden"}`}>{body}</div>
    </div>
  );
}
