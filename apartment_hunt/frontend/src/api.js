// Direct connection to backend — no proxy needed
const BASE = "http://localhost:8000/api";

async function req(method, path, opts = {}) {
  const url = new URL(BASE + path);
  if (opts.params) {
    Object.entries(opts.params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
    });
  }
  const res = await fetch(url, {
    method,
    headers: opts.body ? { "Content-Type": "application/json" } : {},
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} ${path}`);
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  getListings:    (p)    => req("GET",    "/listings/",              { params: p }),
  toggleFavorite: (id)   => req("PATCH",  `/listings/${id}/favorite`),
  deleteListing:  (id)   => req("DELETE", `/listings/${id}`),
  addManual:      (body) => req("POST",   "/listings/manual",        { body }),
  startScrape:    (body) => req("POST",   "/scrape/start",           { body }),
  getStatus:      (id)   => req("GET",    `/scrape/status/${id}`),
};
