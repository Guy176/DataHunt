/**
 * Content script — runs on Facebook Marketplace & group pages.
 * Strategy: read Open Graph meta tags (always present and reliable),
 * then supplement with DOM text extraction for price/rooms/floor.
 */

const EXT_ID = "apt-saver";
let lastUrl = location.href;

// ─── Utility ────────────────────────────────────────────────────────────────

function meta(prop) {
  const el =
    document.querySelector(`meta[property="${prop}"]`) ||
    document.querySelector(`meta[name="${prop}"]`);
  return el ? el.getAttribute("content") || "" : "";
}

function bodyText() {
  return document.body.innerText || "";
}

function extractPrice(text) {
  // Matches ₪3,500 or 3500 ₪ or 3,500 NIS etc.
  const patterns = [
    /₪\s*([\d,]+)/,
    /([\d,]+)\s*₪/,
    /([\d,]+)\s*nis/i,
    /([\d,]+)\s*שח/,
    /([\d,]+)\s*שקל/,
    /price[:\s]+([\d,]+)/i,
    /מחיר[:\s]*([\d,]+)/,
  ];
  for (const re of patterns) {
    const m = text.match(re);
    if (m) return parseInt(m[1].replace(/,/g, ""), 10);
  }
  return null;
}

function extractRooms(text) {
  const patterns = [
    /(\d(?:\.\d)?)\s*(?:חדרים|חדר)/,
    /(\d(?:\.\d)?)\s*rooms?/i,
    /rooms?[:\s]+(\d(?:\.\d)?)/i,
    /(\d(?:\.\d)?)\s*br\b/i,
  ];
  for (const re of patterns) {
    const m = text.match(re);
    if (m) return parseFloat(m[1]);
  }
  return null;
}

function extractFloor(text) {
  const patterns = [
    /קומה\s*(\d+)/,
    /floor[:\s]+(\d+)/i,
    /(\d+)(?:st|nd|rd|th)?\s*floor/i,
  ];
  for (const re of patterns) {
    const m = text.match(re);
    if (m) return parseInt(m[1], 10);
  }
  return null;
}

function extractSqm(text) {
  const patterns = [
    /([\d.]+)\s*מ"ר/,
    /([\d.]+)\s*מטר/,
    /([\d.]+)\s*sqm/i,
    /([\d.]+)\s*m²/i,
    /([\d.]+)\s*sq\.?\s*m/i,
  ];
  for (const re of patterns) {
    const m = text.match(re);
    if (m) return parseFloat(m[1]);
  }
  return null;
}

// Parse "City, Neighborhood" or "Neighborhood, City" from location string
function parseLocation(locStr) {
  if (!locStr) return { city: "", neighborhood: "" };
  const parts = locStr.split(",").map((s) => s.trim());
  if (parts.length >= 2) {
    return { city: parts[parts.length - 1], neighborhood: parts[0] };
  }
  return { city: parts[0] || "", neighborhood: "" };
}

// ─── Main extraction ─────────────────────────────────────────────────────────

function extractListing() {
  const text = bodyText();
  const ogTitle = meta("og:title");
  const ogDesc = meta("og:description");
  const ogImage = meta("og:image");
  const ogUrl = meta("og:url") || location.href;

  // Location — Facebook usually puts it in og:description or visible text
  const locMatch =
    ogDesc.match(/(?:in|ב-?|located in)\s+([^•\n,]+(?:,\s*[^\n•]+)?)/i) || [];
  const locStr = locMatch[1] || "";
  const { city, neighborhood } = parseLocation(locStr);

  const combinedText = `${ogTitle} ${ogDesc} ${text}`;
  const price = extractPrice(combinedText);
  const rooms = extractRooms(combinedText);
  const floor = extractFloor(combinedText);
  const size_sqm = extractSqm(combinedText);

  // Seller name — heuristic
  const sellerMatch = text.match(/(?:seller|agent|contact|מוכר|פרטי קשר)[:\s]+([^\n]{2,40})/i);
  const contactName = sellerMatch ? sellerMatch[1].trim() : "";

  return {
    title: ogTitle || document.title,
    description: ogDesc,
    price,
    rooms,
    floor,
    size_sqm,
    city,
    neighborhood,
    address: locStr,
    image_url: ogImage,
    url: ogUrl,
    contact_name: contactName,
    source_hint: location.href.includes("/marketplace/") ? "marketplace" : "group",
  };
}

// ─── Floating save button ─────────────────────────────────────────────────────

function isListingPage() {
  return (
    /\/marketplace\/item\//.test(location.pathname) ||
    /\/marketplace\/\d+/.test(location.pathname)
  );
}

function injectSaveButton() {
  if (document.getElementById(`${EXT_ID}-btn`)) return;

  const btn = document.createElement("button");
  btn.id = `${EXT_ID}-btn`;
  btn.className = `${EXT_ID}-fab`;
  btn.title = "Save to Apartment Search";
  btn.innerHTML = `
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
      <polyline points="17 21 17 13 7 13 7 21"/>
      <polyline points="7 3 7 8 15 8"/>
    </svg>
    <span>Save Listing</span>
  `;

  btn.addEventListener("click", () => {
    const data = extractListing();
    chrome.runtime.sendMessage({ type: "OPEN_SAVE_PANEL", data });
  });

  document.body.appendChild(btn);
}

// Inject "Save" buttons on group post feeds
function injectGroupButtons() {
  // Find posts that look like rental ads (contain price patterns)
  const articles = document.querySelectorAll('[role="article"]');
  articles.forEach((article) => {
    if (article.querySelector(`.${EXT_ID}-post-btn`)) return;

    const text = article.innerText || "";
    if (!extractPrice(text) && !extractRooms(text)) return; // not a listing

    const btn = document.createElement("button");
    btn.className = `${EXT_ID}-post-btn`;
    btn.textContent = "💾 Save to Apartment Search";
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const data = extractFromArticle(article);
      chrome.runtime.sendMessage({ type: "OPEN_SAVE_PANEL", data });
    });

    // Append after article actions bar
    const actionsBar = article.querySelector('[aria-label*="actions"], [data-testid*="actions"]');
    const target = actionsBar || article;
    target.appendChild(btn);
  });
}

function extractFromArticle(article) {
  const text = article.innerText || "";
  const img = article.querySelector("img[src*='scontent']");
  const link = article.querySelector('a[href*="/groups/"]') || article.querySelector("a");
  const url = link ? link.href : location.href;

  // Try to grab the post author
  const authorEl = article.querySelector('h3 a, h4 a, strong a');
  const contactName = authorEl ? authorEl.innerText.trim() : "";

  return {
    title: text.split("\n")[0].trim().slice(0, 120) || "Group Post Listing",
    description: text.slice(0, 500),
    price: extractPrice(text),
    rooms: extractRooms(text),
    floor: extractFloor(text),
    size_sqm: extractSqm(text),
    city: "",
    neighborhood: "",
    address: "",
    image_url: img ? img.src : "",
    url,
    contact_name: contactName,
    source_hint: "group",
  };
}

// ─── Route change detection (Facebook is SPA) ───────────────────────────────

function onNavigate() {
  if (isListingPage()) {
    // Wait for Facebook's content to load
    setTimeout(injectSaveButton, 1500);
    setTimeout(injectSaveButton, 3000);
  }
  if (location.pathname.includes("/groups/")) {
    setTimeout(injectGroupButtons, 2000);
    setTimeout(injectGroupButtons, 4000);
  }
}

// Observe URL changes (Facebook uses history.pushState)
const observer = new MutationObserver(() => {
  if (location.href !== lastUrl) {
    lastUrl = location.href;
    onNavigate();
  }
  // Re-scan group posts as new ones load
  if (location.pathname.includes("/groups/")) {
    injectGroupButtons();
  }
});

observer.observe(document.body, { childList: true, subtree: true });

// Initial run
onNavigate();

// Listen for message from popup asking for current page data
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "GET_LISTING_DATA") {
    sendResponse(extractListing());
  }
});
