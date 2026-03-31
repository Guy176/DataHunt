import React, { useState } from "react";
import { PlusCircle, Info } from "lucide-react";
import { addManualListing } from "../services/api";

const EMPTY = {
  title: "", price: "", rooms: "", floor: "", size_sqm: "",
  city: "", neighborhood: "", street: "", address: "",
  description: "", image_url: "", url: "", contact_name: "", phone: "",
};

export default function AddManualListing({ onAdded }) {
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  function set(k, v) { setForm((f) => ({ ...f, [k]: v })); }

  async function submit(e) {
    e.preventDefault();
    if (!form.title) { setError("Title is required"); return; }
    setSaving(true); setError(""); setSuccess(false);
    try {
      const payload = Object.fromEntries(
        Object.entries(form).map(([k, v]) => [
          k,
          ["price", "rooms", "floor", "size_sqm"].includes(k) && v !== ""
            ? Number(v)
            : v || null,
        ])
      );
      await addManualListing(payload);
      setSuccess(true);
      setForm(EMPTY);
      onAdded?.();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to add listing");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-lg mx-auto">
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-3 mb-4 flex gap-2 text-sm text-blue-700">
        <Info size={16} className="shrink-0 mt-0.5" />
        <p>
          Found something on <strong>Facebook Marketplace</strong> or another source?
          Add it here manually to keep everything in one place.
        </p>
      </div>

      <form
        onSubmit={submit}
        className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4 space-y-4"
      >
        <h2 className="font-semibold text-slate-700 flex items-center gap-2">
          <PlusCircle size={18} className="text-brand-600" />
          Add Listing Manually
        </h2>

        <FField label="Title *">
          <input className="input" required value={form.title} onChange={(e) => set("title", e.target.value)} placeholder="3 rooms in Florentine, Tel Aviv" />
        </FField>

        <div className="grid grid-cols-2 gap-3">
          <FField label="Price (₪/mo)">
            <input type="number" className="input" value={form.price} onChange={(e) => set("price", e.target.value)} placeholder="4500" min={0} />
          </FField>
          <FField label="Rooms">
            <input type="number" step="0.5" className="input" value={form.rooms} onChange={(e) => set("rooms", e.target.value)} placeholder="3" min={0} />
          </FField>
          <FField label="Floor">
            <input type="number" className="input" value={form.floor} onChange={(e) => set("floor", e.target.value)} placeholder="2" />
          </FField>
          <FField label="Size (m²)">
            <input type="number" className="input" value={form.size_sqm} onChange={(e) => set("size_sqm", e.target.value)} placeholder="75" min={0} />
          </FField>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <FField label="City">
            <input className="input rtl-text" value={form.city} onChange={(e) => set("city", e.target.value)} placeholder="תל אביב" />
          </FField>
          <FField label="Neighborhood">
            <input className="input rtl-text" value={form.neighborhood} onChange={(e) => set("neighborhood", e.target.value)} placeholder="פלורנטין" />
          </FField>
        </div>

        <FField label="Street">
          <input className="input rtl-text" value={form.street} onChange={(e) => set("street", e.target.value)} placeholder="רחוב..." />
        </FField>

        <FField label="Listing URL">
          <input type="url" className="input" value={form.url} onChange={(e) => set("url", e.target.value)} placeholder="https://www.facebook.com/marketplace/..." />
        </FField>

        <FField label="Image URL">
          <input type="url" className="input" value={form.image_url} onChange={(e) => set("image_url", e.target.value)} placeholder="https://..." />
        </FField>

        <div className="grid grid-cols-2 gap-3">
          <FField label="Contact Name">
            <input className="input" value={form.contact_name} onChange={(e) => set("contact_name", e.target.value)} placeholder="שם" />
          </FField>
          <FField label="Phone">
            <input type="tel" className="input" value={form.phone} onChange={(e) => set("phone", e.target.value)} placeholder="05x-xxxxxxx" />
          </FField>
        </div>

        <FField label="Notes / Description">
          <textarea className="input resize-none h-20" value={form.description} onChange={(e) => set("description", e.target.value)} placeholder="Any notes..." />
        </FField>

        {error && <p className="text-red-600 text-sm">{error}</p>}
        {success && <p className="text-green-600 text-sm font-medium">Listing added!</p>}

        <button
          type="submit"
          disabled={saving}
          className="w-full bg-brand-600 hover:bg-brand-700 disabled:opacity-60 text-white font-semibold py-3 rounded-xl transition-colors"
        >
          {saving ? "Adding…" : "Add Listing"}
        </button>
      </form>
    </div>
  );
}

function FField({ label, children }) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">{label}</label>
      {children}
    </div>
  );
}
