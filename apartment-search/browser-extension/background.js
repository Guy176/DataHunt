/**
 * Service worker — handles:
 *  1. Single-listing save (from FAB / group post button)
 *  2. Multi-tab group scan ("Scan All Tabs" feature)
 */

// ── Single listing save (triggered by content script FAB) ────────────────────

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "OPEN_SAVE_PANEL") {
    chrome.storage.session.set({ pendingListing: msg.data });
    chrome.action.openPopup().catch(() => {
      // Fallback: badge notification
      chrome.action.setBadgeText({ text: "1" });
      chrome.action.setBadgeBackgroundColor({ color: "#2563eb" });
    });
    return;
  }

  // POST a single listing to the API
  if (msg.type === "SAVE_LISTING") {
    chrome.storage.sync.get({ apiUrl: "http://localhost:8000" }, ({ apiUrl }) => {
      postListing(apiUrl, msg.listing)
        .then((result) => sendResponse({ ok: true, result }))
        .catch((err) => sendResponse({ ok: false, error: err.message }));
    });
    return true;
  }

  // ── Multi-tab group scan ────────────────────────────────────────────────

  if (msg.type === "SCAN_ALL_TABS") {
    chrome.storage.sync.get({ apiUrl: "http://localhost:8000" }, async ({ apiUrl }) => {
      try {
        const result = await scanAllGroupTabs(apiUrl);
        sendResponse({ ok: true, ...result });
      } catch (err) {
        sendResponse({ ok: false, error: err.message });
      }
    });
    return true; // async
  }
});

// ── Multi-tab scanner ────────────────────────────────────────────────────────

async function scanAllGroupTabs(apiUrl) {
  // Find all open Facebook group tabs
  const tabs = await chrome.tabs.query({
    url: [
      "https://www.facebook.com/groups/*",
      "https://m.facebook.com/groups/*",
    ],
  });

  if (tabs.length === 0) {
    return { saved: 0, skipped: 0, tabs: 0, message: "No Facebook group tabs found." };
  }

  // Track already-saved URLs to avoid duplicates across tabs
  const existingUrls = await getExistingUrls(apiUrl);

  let saved = 0;
  let skipped = 0;
  const errors = [];

  for (const tab of tabs) {
    try {
      // Inject and run the scanner script in the tab
      const [{ result: listings }] = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ["content/group_scanner.js"],
      });

      if (!listings || !listings.length) continue;

      for (const listing of listings) {
        if (listing.url && existingUrls.has(listing.url)) {
          skipped++;
          continue;
        }
        try {
          await postListing(apiUrl, listing);
          if (listing.url) existingUrls.add(listing.url);
          saved++;
          // Small delay to not hammer the API
          await sleep(150);
        } catch (err) {
          errors.push(err.message);
          skipped++;
        }
      }
    } catch (err) {
      errors.push(`Tab "${tab.title}": ${err.message}`);
    }
  }

  return {
    saved,
    skipped,
    tabs: tabs.length,
    errors: errors.slice(0, 5),
    message: `Scanned ${tabs.length} group tab(s). Saved ${saved} new listings, skipped ${skipped}.`,
  };
}

// ── API helpers ──────────────────────────────────────────────────────────────

async function postListing(apiUrl, listing) {
  const url = `${apiUrl.replace(/\/$/, "")}/api/listings/manual`;
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(listing),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`API ${resp.status}: ${body.slice(0, 120)}`);
  }
  return resp.json();
}

async function getExistingUrls(apiUrl) {
  try {
    const resp = await fetch(
      `${apiUrl.replace(/\/$/, "")}/api/listings/?limit=500&source=manual`,
      { signal: AbortSignal.timeout(5000) }
    );
    if (!resp.ok) return new Set();
    const listings = await resp.json();
    return new Set(listings.map((l) => l.url).filter(Boolean));
  } catch {
    return new Set();
  }
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}
