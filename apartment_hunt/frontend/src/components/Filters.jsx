import React, { useState } from "react";

const CITIES = [
  "תל אביב","ירושלים","חיפה","ראשון לציון","פתח תקווה","אשדוד","נתניה",
  "באר שבע","בני ברק","חולון","רמת גן","אשקלון","רחובות","בת ים",
  "כפר סבא","הרצליה","חדרה","מודיעין","לוד","אילת","גבעתיים","בית שמש",
];

const NEIGHBORHOODS = {
  "תל אביב":       ["יפו","נווה צדק","פלורנטין","נווה שאנן","לב תל אביב","הצפון הישן","הצפון החדש","רמת אביב","רמת אביב ג","כרם התימנים","שפירא","מונטיפיורי"],
  "ירושלים":       ["רחביה","טלביה","בקעה","קטמון","גילה","הר חומה","פסגת זאב","רמות אלון","מעלות דפנה","נווה יעקב","גבעת שאול","קריית יובל","בית וגן","ניות","מחנה יהודה"],
  "חיפה":          ["כרמל מרכזי","כרמל צרפתי","אחוזה","נווה שאנן","רמות רמז","קריית חיים מערבית","קריית חיים מזרחית","הדר הכרמל","מרכז הכרמל","נאות פרס","בת גלים"],
  "ראשון לציון":   ["נחלת יהודה","רמת אליהו","ניר צבי","ורדיה"],
  "פתח תקווה":     ["כפר גנים","שכונת התקווה","אם המושבות","קריית ספיר"],
  "רמת גן":        ["הבורסה","הביל\"ויים","הגפן ונחלת גנים","הלל","הראשונים","ותיקים","חרוזים","לב העיר","נווה יהושע","ציר זבוטינסקי","קרית בורוכוב","רמת אפעל","רמת חן","רמת עמידר","רמת שקמה","שיכון מזרחי","תל בנימין","תל גנים"],
  "נתניה":         ["אגמים","עיר ימים","פולג","ניצנים","עמידר","קריית נורדאו"],
  "באר שבע":       ["רמות","דלתא","הנגב","ט","נווה זאב","כרמים"],
  "הרצליה":        ["הרצליה פיתוח","הרצליה ב","ניר זוי"],
  "חולון":         ["קריית השרון","קריית עגנון","חוף השרון","ניר העמק"],
  "בת ים":         ["מרכז העיר","עיר הים","קריית שלום"],
  "גבעתיים":       ["בורוכוב","קריית יוסף","ויצמן"],
  "כפר סבא":       ["מרכז העיר","נווה ים","אפק","עמישב"],
  "מודיעין":       ["גנות","מכבים","ספיר","אמנון","ענבל"],
};

const ROOMS = ["1","1.5","2","2.5","3","3.5","4","4.5","5","5.5","6+"];
const SORTS = [
  { v: "scraped_at", l: "Newest"  },
  { v: "price",      l: "Price"   },
  { v: "rooms",      l: "Rooms"   },
  { v: "floor",      l: "Floor"   },
  { v: "size_sqm",   l: "Size m²" },
];

function Label({ children }) {
  return (
    <label className="block mb-1.5 text-[10px] font-semibold tracking-widest uppercase"
      style={{ color: "var(--text-muted)" }}>
      {children}
    </label>
  );
}

function Field({ children }) {
  return <div className="mb-4">{children}</div>;
}

const inputCls = "w-full px-3 py-2 text-sm rounded-lg";

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

  const nbhds     = NEIGHBORHOODS[filters.city] || [];
  const hasFilter = !!(filters.city || filters.min_price || filters.max_price || filters.min_rooms || filters.max_rooms);

  const body = (
    <div className="p-5 space-y-0">

      {/* City */}
      <Field>
        <Label>City</Label>
        <select value={filters.city} onChange={e => set("city", e.target.value)} className={inputCls}>
          <option value="">All cities</option>
          {CITIES.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      </Field>

      {/* Neighborhood */}
      <Field>
        <Label>Neighborhood</Label>
        <select value={filters.neighborhood} onChange={e => set("neighborhood", e.target.value)}
          className={inputCls} disabled={!nbhds.length}
          style={{ opacity: nbhds.length ? 1 : 0.4 }}>
          <option value="">All neighborhoods</option>
          {nbhds.map(n => <option key={n} value={n}>{n}</option>)}
        </select>
      </Field>

      {/* Divider */}
      <div className="h-px my-5" style={{ background: "var(--border)" }} />

      {/* Price */}
      <Field>
        <Label>Monthly rent ₪</Label>
        <div className="flex gap-2">
          <input type="number" placeholder="Min" value={filters.min_price}
            onChange={e => set("min_price", e.target.value)} className={`${inputCls} w-1/2`}
            style={{ fontFamily: "'Fira Code', monospace" }} />
          <input type="number" placeholder="Max" value={filters.max_price}
            onChange={e => set("max_price", e.target.value)} className={`${inputCls} w-1/2`}
            style={{ fontFamily: "'Fira Code', monospace" }} />
        </div>
      </Field>

      {/* Rooms */}
      <Field>
        <Label>Rooms</Label>
        <div className="flex gap-2">
          {[["min_rooms","Min"], ["max_rooms","Max"]].map(([key, ph]) => (
            <select key={key} value={filters[key]} onChange={e => set(key, e.target.value)}
              className={`${inputCls} w-1/2`}>
              <option value="">{ph}</option>
              {ROOMS.map(r => <option key={r} value={r.replace("+","")}>{r}</option>)}
            </select>
          ))}
        </div>
      </Field>

      {/* Floor */}
      <Field>
        <Label>Floor</Label>
        <div className="flex gap-2">
          <input type="number" placeholder="Min" value={filters.min_floor}
            onChange={e => set("min_floor", e.target.value)} className={`${inputCls} w-1/2`} />
          <input type="number" placeholder="Max" value={filters.max_floor}
            onChange={e => set("max_floor", e.target.value)} className={`${inputCls} w-1/2`} />
        </div>
      </Field>

      {/* Divider */}
      <div className="h-px my-5" style={{ background: "var(--border)" }} />

      {/* Sources */}
      <Field>
        <Label>Sources</Label>
        <div className="flex gap-3">
          {[
            { id: "yad2",   label: "Yad2",   color: "#FF6B35" },
            { id: "madlan", label: "Madlan",  color: "#A855F7" },
          ].map(src => (
            <button key={src.id} onClick={() => toggleSource(src.id)}
              className="flex-1 py-2 rounded-lg text-xs font-semibold tracking-wider uppercase transition-all"
              style={filters.sources.includes(src.id)
                ? { background: `${src.color}22`, color: src.color, border: `1px solid ${src.color}55` }
                : { background: "var(--surface-2)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>
              {src.label}
            </button>
          ))}
        </div>
      </Field>

      {/* Sort */}
      <Field>
        <Label>Sort by</Label>
        <div className="flex gap-2">
          <select value={filters.sort_by} onChange={e => set("sort_by", e.target.value)}
            className={`${inputCls} flex-1`}>
            {SORTS.map(s => <option key={s.v} value={s.v}>{s.l}</option>)}
          </select>
          <select value={filters.sort_order} onChange={e => set("sort_order", e.target.value)}
            className={`${inputCls} w-24`}>
            <option value="desc">↓ Desc</option>
            <option value="asc">↑ Asc</option>
          </select>
        </div>
      </Field>

      {/* Buttons */}
      <div className="flex gap-2 pt-2">
        <button onClick={onSearch} disabled={loading}
          className="flex-1 py-2.5 rounded-xl text-xs font-bold tracking-widest uppercase transition-all disabled:opacity-50"
          style={{ background: "var(--accent)", color: "#080C14" }}>
          {loading ? "LOADING…" : "SEARCH"}
        </button>
        {hasFilter && (
          <button onClick={() => { onChange(DEFAULTS_EXPORT); setTimeout(onSearch, 50); }}
            className="px-4 py-2.5 rounded-xl text-xs font-semibold tracking-wider transition-all"
            style={{ color: "var(--text-muted)", border: "1px solid var(--border)" }}>
            RESET
          </button>
        )}
      </div>
    </div>
  );

  return (
    <div className="rounded-2xl overflow-hidden"
      style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>

      {/* Mobile toggle */}
      <button onClick={() => setOpen(o => !o)}
        className="lg:hidden w-full flex items-center justify-between px-5 py-4">
        <span className="text-xs font-bold tracking-widest uppercase" style={{ color: "var(--text-muted)" }}>
          Filters {hasFilter && <span style={{ color: "var(--accent)" }}>●</span>}
        </span>
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>{open ? "▲" : "▼"}</span>
      </button>

      <div className={`lg:block ${open ? "block" : "hidden"}`}>{body}</div>
    </div>
  );
}

// exported for reset — mirrors DEFAULTS in App
const DEFAULTS_EXPORT = {
  city: "", neighborhood: "", min_price: "", max_price: "",
  min_rooms: "", max_rooms: "", min_floor: "", max_floor: "",
  sources: ["yad2", "madlan"], sort_by: "scraped_at", sort_order: "desc",
};
