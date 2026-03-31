// ── Helpers ───────────────────────────────────────────────────────────────────

function $(id)       { return document.getElementById(id); }
function show(id)    { $(id).classList.remove("hidden"); }
function hide(id)    { $(id).classList.add("hidden"); }
function val(id)     { return $(id).value.trim(); }
function setVal(id, v) { if (v != null && v !== "") $(id).value = v; }

// ── Tab switching ─────────────────────────────────────────────────────────────

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const target = btn.dataset.tab;
    $("tab-save").classList.toggle("hidden", target !== "save");
    $("tab-scan").classList.toggle("hidden", target !== "scan");
    if (target === "scan") checkGroupTabs();
  });
});

// ── Save tab: populate form ───────────────────────────────────────────────────

function populateForm(data) {
  if (!data) return;

  setVal("f-title", data.title);
  setVal("f-price", data.price);
  setVal("f-rooms", data.rooms);
  setVal("f-floor", data.floor);
  setVal("f-sqm", data.size_sqm);
  setVal("f-city", data.city);
  setVal("f-neighborhood", data.neighborhood);
  setVal("f-contact", data.contact_name);
  setVal("f-notes", data.description);
  $("f-url").value   = data.url || "";
  $("f-image").value = data.image_url || "";

  if (data.image_url) {
    $("preview-img").src = data.image_url;
    show("img-preview");
  }

  const isMarketplace =
    data.source_hint === "marketplace" ||
    (data.url && data.url.includes("/marketplace/"));
  const badge = $("source-label");
  badge.textContent = isMarketplace ? "Marketplace" : "Group";
  badge.className   = `badge ${isMarketplace ? "badge-marketplace" : "badge-group"}`;

  try {
    $("page-url").textContent = data.url
      ? new URL(data.url).pathname.slice(0, 46)
      : "";
  } catch { $("page-url").textContent = ""; }

  show("source-bar");
  show("listing-form");
  hide("not-fb");
}

async function initSaveTab() {
  // 1. Check for pending listing from FAB/post-button
  const session = await new Promise((res) =>
    chrome.storage.session.get("pendingListing", res)
  );
  if (session.pendingListing) {
    populateForm(session.pendingListing);
    chrome.storage.session.remove("pendingListing");
    return;
  }

  // 2. Ask content script for current page data
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.url?.includes("facebook.com")) {
      show("not-fb");
      return;
    }
    const data = await chrome.tabs.sendMessage(tab.id, { type: "GET_LISTING_DATA" });
    if (data && (data.price || data.rooms || data.title)) {
      populateForm(data);
    } else {
      show("not-fb");
    }
  } catch {
    show("not-fb");
  }
}

// ── Save form submit ──────────────────────────────────────────────────────────

$("listing-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  hide("error-msg");
  hide("success-msg");

  const title = val("f-title");
  if (!title) {
    $("error-msg").textContent = "Title is required.";
    show("error-msg");
    return;
  }

  const listing = {
    title,
    price:    $("f-price").value ? parseInt($("f-price").value, 10)     : null,
    rooms:    $("f-rooms").value ? parseFloat($("f-rooms").value)        : null,
    floor:    $("f-floor").value ? parseInt($("f-floor").value, 10)      : null,
    size_sqm: $("f-sqm").value   ? parseFloat($("f-sqm").value)          : null,
    city:          val("f-city")         || null,
    neighborhood:  val("f-neighborhood") || null,
    description:   val("f-notes")        || null,
    contact_name:  val("f-contact")      || null,
    url:       $("f-url").value   || null,
    image_url: $("f-image").value || null,
  };

  const btn = $("save-btn");
  btn.disabled    = true;
  btn.textContent = "Saving…";

  const response = await new Promise((res) =>
    chrome.runtime.sendMessage({ type: "SAVE_LISTING", listing }, res)
  );

  btn.disabled = false;
  btn.innerHTML = saveBtnInner("Save to Apartment Search");

  if (response?.ok) {
    $("success-msg").textContent = "Listing saved!";
    show("success-msg");
    setTimeout(() => window.close(), 1800);
  } else {
    $("error-msg").textContent =
      response?.error || "Save failed. Is the backend running?";
    show("error-msg");
  }
});

// ── Scan All Tabs ─────────────────────────────────────────────────────────────

async function checkGroupTabs() {
  const tabs = await chrome.tabs.query({
    url: [
      "https://www.facebook.com/groups/*",
      "https://m.facebook.com/groups/*",
    ],
  });
  const row = $("tab-count-row");
  const label = $("tab-count-label");
  if (tabs.length > 0) {
    label.textContent = `${tabs.length} Facebook group tab${tabs.length > 1 ? "s" : ""} found and ready to scan`;
    show("tab-count-row");
  } else {
    label.textContent = "No Facebook group tabs open — open some groups first";
    row.style.background = "#fef9c3";
    row.style.borderColor = "#fde68a";
    row.style.color = "#92400e";
    show("tab-count-row");
  }
}

$("scan-btn").addEventListener("click", async () => {
  const btn = $("scan-btn");
  btn.disabled = true;
  btn.textContent = "Scanning…";

  hide("scan-result");
  show("scan-progress");
  $("progress-fill").style.width = "15%";
  $("progress-label").textContent = "Starting scan…";

  // Animate progress bar while waiting
  let pct = 15;
  const ticker = setInterval(() => {
    pct = Math.min(pct + Math.random() * 8, 88);
    $("progress-fill").style.width = `${pct}%`;
  }, 800);

  const response = await new Promise((res) =>
    chrome.runtime.sendMessage({ type: "SCAN_ALL_TABS" }, res)
  );

  clearInterval(ticker);
  $("progress-fill").style.width = "100%";
  await new Promise((r) => setTimeout(r, 300));
  hide("scan-progress");

  const resultEl = $("scan-result");
  if (response?.ok) {
    const { saved, skipped, tabs, message } = response;
    resultEl.className = saved > 0 ? "scan-result success" : "scan-result info";
    resultEl.innerHTML = `
      <div style="font-size:22px;margin-bottom:4px">${saved > 0 ? "🎉" : "ℹ️"}</div>
      <strong>${message}</strong>
      <div style="margin-top:6px;font-size:11px;font-weight:400;opacity:0.8">
        Tabs scanned: ${tabs} &nbsp;·&nbsp; New: ${saved} &nbsp;·&nbsp; Skipped: ${skipped}
      </div>
    `;
  } else {
    resultEl.className = "scan-result error";
    resultEl.textContent = response?.error || "Scan failed. Is the backend running?";
  }
  show("scan-result");

  btn.disabled = false;
  btn.innerHTML = scanBtnInner("Scan Again");
});

// ── Settings ──────────────────────────────────────────────────────────────────

$("settings-btn").addEventListener("click", () => {
  chrome.runtime.openOptionsPage();
});

// ── Button HTML helpers ───────────────────────────────────────────────────────

function saveBtnInner(label) {
  return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>${label}`;
}
function scanBtnInner(label) {
  return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>${label}`;
}

// ── Init ──────────────────────────────────────────────────────────────────────
initSaveTab();
