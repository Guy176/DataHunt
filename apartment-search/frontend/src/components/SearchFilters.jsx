import React, { useState } from "react";
import { SlidersHorizontal, ChevronDown, ChevronUp, X } from "lucide-react";

const CITIES = [
  "תל אביב", "ירושלים", "חיפה", "ראשון לציון", "פתח תקווה",
  "אשדוד", "נתניה", "באר שבע", "בני ברק", "חולון", "רמת גן",
  "אשקלון", "רחובות", "בת ים", "כפר סבא", "הרצליה", "חדרה",
  "מודיעין", "לוד", "אילת",
];

// מקור: ויקיפדיה עברית, אתרי עיריות, המכלול
const NEIGHBORHOODS = {
  // תל אביב-יפו: 9 רובעים מנהלתיים — שכונות לפי רובע (ויקיפדיה + עיריית ת"א)
  "תל אביב": [
    // רובע 1+2 — עבר הירקון (צפון-מערב וצפון-מזרח)
    "רמת אביב", "נאות אפקה", "אפקה", "נווה אביבים", "הדר יוסף",
    "צהלה", "שיכון דן", "רמת החייל",
    // רובע 3 — הצפון הישן
    "הצפון הישן",
    // רובע 4 — הצפון החדש
    "הצפון החדש", "בבלי", "פארק צמרת", "גבעת עמל",
    // רובע 5 — לב העיר
    "לב העיר", "נווה צדק", "כרם התימנים",
    // רובע 6 — מרכז עסקים
    "מונטיפיורי", "שכונת הרכבת",
    // רובע 7 — יפו ואבו כביר
    "יפו", "עג'מי", "גבעת עלייה", "נווה עופר", "אבו כביר",
    // רובע 8 — דרום
    "נווה שאנן", "פלורנטין", "שפירא", "קרית שלום",
    // רובע 9 — דרום-מזרח
    "שכונת התקווה", "כפר שלם", "נחלת יצחק", "יד אליהו",
    "עזרא", "הארגזים",
  ],
  // ירושלים: לפי אתר עיריית ירושלים ו-Wikipedia (~160 שכונות, כאן הבולטות)
  "ירושלים": [
    "רחביה", "טלביה", "קטמון הישנה", "קטמון החדשה", "גבעת מרדכי",
    "בקעה", "תלפיות", "ארנונה", "גילה", "הר חומה", "צור באהר",
    "קרית מנחם", "עיר גנים", "קרית יובל", "פת", "ניות",
    "בית הכרם", "בית וגן", "קרית משה", "גבעת שאול", "הר נוף",
    "רמות אלון", "פסגת זאב", "נווה יעקב", "מעלות דפנה",
    "הגבעה הצרפתית", "נחלאות", "מחנה יהודה", "מאה שערים",
    "עין כרם", "מלחה", "גבעת המטוס", "המושבה הגרמנית",
    "רמת שרת", "רמת דניה",
  ],
  // חיפה: לפי פורטל הנתונים הפתוח של עיריית חיפה (odata.org.il)
  "חיפה": [
    "כרמל מרכזי", "כרמליה", "דניה", "אחוזה", "רמת הנשיא",
    "רמת ויצמן", "רמות ספיר", "נווה שאנן", "הדר הכרמל",
    "עיר תחתית", "המושבה הגרמנית", "בת גלים", "קרית חיים מערבית",
    "קרית חיים מזרחית", "קרית שפרינצק", "קרית אליעזר",
    "חליסה", "ואדי ניסנאס", "נאות פרס",
  ],
  "ראשון לציון": [
    "נחלת יהודה", "מרכז העיר", "רמת אליהו", "יובלים",
    "בנה ביתך", "נווה הדרים", "נווה יהודה", "גני ים", "משכנות",
  ],
  "פתח תקווה": [
    "מרכז העיר", "כפר גנים א", "כפר גנים ב", "כפר גנים ג",
    "סגולה", "שיכון ותיקים", "אם המושבות", "גני סביון",
  ],
  // נתניה — הגדרה אחת בלבד (תוקן: היה מוגדר פעמיים)
  "נתניה": [
    "מרכז העיר", "עיר ימים", "קרית נורדאו", "קרית השרון",
    "רמת פולג", "אגמים", "נווה עמיקם", "גני הדר", "שכונת פולג",
  ],
  "באר שבע": [
    "שכונה א", "שכונה ב", "שכונה ג", "שכונה ד", "שכונה ה", "שכונה ו",
    "נאות לון", "נאות אשכול", "נאות הנגב", "נאות אפרים",
    "גבעות בר", "רמת בגין",
  ],
  "בני ברק": [
    "מרכז העיר", "פרדס כץ", "קרית הגר\"א", "זיכרון מאיר", "שומרי אמונים",
  ],
  "חולון": [
    "מרכז העיר", "קרית שרת", "שיכון ז", "רובע ד",
  ],
  "רמת גן": [
    "מרכז העיר", "בורוכוב", "שיכון ותיקים", "נאות גנים",
    "קרית קרינגי", "רמת עדן",
  ],
  "אשדוד": [
    "רובע א", "רובע ב", "רובע ג", "רובע ד", "רובע ה",
    "רובע ו", "רובע ז", "רובע ח", "רובע ט", "לב ים",
  ],
  "בת ים": [
    "מרכז העיר", "רמת יוסף", "גבעת הים",
  ],
  "כפר סבא": [
    "מרכז העיר", "רמת כפר סבא", "גנים", "עין סמריה",
  ],
  "הרצליה": [
    "הרצליה פיתוח", "הרצליה ב", "נווה עמל", "גליל ים",
  ],
  "אשקלון": [
    "ברנע", "מיגדל", "ממשית", "צאלים", "אפרידר", "גיורא", "שמשון",
  ],
  "רחובות": [
    "מרכז העיר", "קרית משה", "נאות גנים", "גנות", "שכונת הפועלים",
  ],
  "מודיעין": [
    "מורשה", "אמירים", "ספיר", "גנות", "שקמה", "הגנים", "המעיין",
  ],
};

// Returns neighborhoods for selected city, or all neighborhoods if no city selected
function getNeighborhoods(city) {
  if (city && NEIGHBORHOODS[city]) return NEIGHBORHOODS[city];
  if (!city) return Object.values(NEIGHBORHOODS).flat().sort((a, b) => a.localeCompare(b, "he"));
  return [];
}

const ROOM_OPTIONS = ["1", "1.5", "2", "2.5", "3", "3.5", "4", "4.5", "5", "6+"];

const SOURCES = [
  { id: "yad2",   label: "Yad2",   cls: "badge-yad2"   },
  { id: "madlan", label: "Madlan", cls: "badge-madlan" },
];

const DEFAULT_FILTERS = {
  min_price: "",
  max_price: "",
  min_rooms: "",
  max_rooms: "",
  min_floor: "",
  max_floor: "",
  city: "",
  neighborhood: "",
  sources: ["yad2", "madlan"],
  sort_by: "scraped_at",
  sort_order: "desc",
};

export default function SearchFilters({ filters, onChange, onSearch, loading }) {
  const [open, setOpen] = useState(true);

  function set(key, val) {
    onChange({ ...filters, [key]: val });
  }

  function toggleSource(id) {
    const next = filters.sources.includes(id)
      ? filters.sources.filter((s) => s !== id)
      : [...filters.sources, id];
    onChange({ ...filters, sources: next });
  }

  function reset() {
    onChange(DEFAULT_FILTERS);
  }

  const hasFilters = Object.entries(filters).some(([k, v]) => {
    if (k === "sources") return v.length !== 2;
    if (k === "sort_by") return v !== "scraped_at";
    if (k === "sort_order") return v !== "desc";
    return v !== "";
  });

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 font-semibold text-slate-700"
      >
        <span className="flex items-center gap-2">
          <SlidersHorizontal size={18} className="text-brand-600" />
          Filters
          {hasFilters && (
            <span className="bg-brand-600 text-white text-xs px-1.5 py-0.5 rounded-full">
              Active
            </span>
          )}
        </span>
        {open ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-4 border-t border-slate-100 pt-4">

          {/* City */}
          <Field label="City">
            <select
              value={filters.city}
              onChange={(e) => onChange({ ...filters, city: e.target.value, neighborhood: "" })}
              className="input"
            >
              <option value="">All cities</option>
              {CITIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </Field>

          {/* Neighborhood */}
          <Field label="Neighborhood">
            <select
              value={filters.neighborhood}
              onChange={(e) => set("neighborhood", e.target.value)}
              className="input rtl-text"
            >
              <option value="">All neighborhoods</option>
              {getNeighborhoods(filters.city).map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </Field>

          {/* Price */}
          <Field label="Monthly Rent (₪)">
            <div className="flex gap-2">
              <input
                type="number"
                placeholder="Min"
                value={filters.min_price}
                onChange={(e) => set("min_price", e.target.value)}
                className="input flex-1"
                min={0}
              />
              <input
                type="number"
                placeholder="Max"
                value={filters.max_price}
                onChange={(e) => set("max_price", e.target.value)}
                className="input flex-1"
                min={0}
              />
            </div>
          </Field>

          {/* Rooms */}
          <Field label="Rooms">
            <div className="flex gap-2">
              <select
                value={filters.min_rooms}
                onChange={(e) => set("min_rooms", e.target.value)}
                className="input flex-1"
              >
                <option value="">Min</option>
                {ROOM_OPTIONS.map((r) => (
                  <option key={r} value={r.replace("+", "")}>
                    {r}
                  </option>
                ))}
              </select>
              <select
                value={filters.max_rooms}
                onChange={(e) => set("max_rooms", e.target.value)}
                className="input flex-1"
              >
                <option value="">Max</option>
                {ROOM_OPTIONS.map((r) => (
                  <option key={r} value={r.replace("+", "")}>
                    {r}
                  </option>
                ))}
              </select>
            </div>
          </Field>

          {/* Floor */}
          <Field label="Floor">
            <div className="flex gap-2">
              <input
                type="number"
                placeholder="Min"
                value={filters.min_floor}
                onChange={(e) => set("min_floor", e.target.value)}
                className="input flex-1"
              />
              <input
                type="number"
                placeholder="Max"
                value={filters.max_floor}
                onChange={(e) => set("max_floor", e.target.value)}
                className="input flex-1"
              />
            </div>
          </Field>

          {/* Sources */}
          <Field label="Sources">
            <div className="flex gap-2 flex-wrap">
              {SOURCES.map((s) => (
                <button
                  key={s.id}
                  onClick={() => toggleSource(s.id)}
                  className={`px-3 py-1 rounded-full text-sm font-medium border transition-all ${
                    filters.sources.includes(s.id)
                      ? `${s.cls} border-current`
                      : "bg-slate-100 text-slate-400 border-transparent"
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </Field>

          {/* Sort */}
          <Field label="Sort by">
            <div className="flex gap-2">
              <select
                value={filters.sort_by}
                onChange={(e) => set("sort_by", e.target.value)}
                className="input flex-1"
              >
                <option value="scraped_at">Newest</option>
                <option value="price">Price</option>
                <option value="rooms">Rooms</option>
                <option value="floor">Floor</option>
                <option value="size_sqm">Size</option>
              </select>
              <select
                value={filters.sort_order}
                onChange={(e) => set("sort_order", e.target.value)}
                className="input w-24"
              >
                <option value="asc">↑ Asc</option>
                <option value="desc">↓ Desc</option>
              </select>
            </div>
          </Field>

          {/* Actions */}
          <div className="flex gap-2 pt-1">
            <button
              onClick={onSearch}
              disabled={loading}
              className="flex-1 bg-brand-600 hover:bg-brand-700 disabled:opacity-60 text-white font-semibold py-2.5 rounded-xl transition-colors"
            >
              {loading ? "Searching…" : "Search"}
            </button>
            {hasFilters && (
              <button
                onClick={reset}
                className="flex items-center gap-1 px-3 py-2.5 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-600 text-sm"
              >
                <X size={14} />
                Reset
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
        {label}
      </label>
      {children}
    </div>
  );
}

// Tailwind doesn't tree-shake dynamic classes — define .input here via @layer
// (handled in index.css via a @layer components block below)
