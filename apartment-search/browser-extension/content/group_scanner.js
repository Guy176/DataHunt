/**
 * group_scanner.js — injected into Facebook group tabs on demand.
 * Scrolls the page, extracts ALL rental posts, and returns them.
 * Triggered by background.js when user clicks "Scan All Tabs".
 */

(async function () {
  const SCROLL_STEPS = 8;
  const SCROLL_DELAY = 1200; // ms between scrolls

  // ── helpers ──────────────────────────────────────────────────────────────

  function extractPrice(text) {
    const patterns = [
      /₪\s*([\d,]+)/, /([\d,]+)\s*₪/,
      /([\d,]+)\s*nis/i, /([\d,]+)\s*שח/, /([\d,]+)\s*שקל/,
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
    ];
    for (const re of patterns) {
      const m = text.match(re);
      if (m) return parseFloat(m[1]);
    }
    return null;
  }

  function extractFloor(text) {
    const patterns = [/קומה\s*(\d+)/, /floor[:\s]+(\d+)/i, /(\d+)(?:st|nd|rd|th)?\s*floor/i];
    for (const re of patterns) {
      const m = text.match(re);
      if (m) return parseInt(m[1], 10);
    }
    return null;
  }

  function extractSqm(text) {
    const patterns = [/([\d.]+)\s*מ"ר/, /([\d.]+)\s*מטר/, /([\d.]+)\s*sqm/i, /([\d.]+)\s*m²/i];
    for (const re of patterns) {
      const m = text.match(re);
      if (m) return parseFloat(m[1]);
    }
    return null;
  }

  const RENTAL_KEYWORDS = [
    "להשכרה", "שכירות", "שכ\"ד", "שכד", "for rent", "to rent",
    "rental", "דירה", "apartment", "חדרים", "חדר", "קומה",
    "₪", "שח", "nis",
  ];

  function isRentalPost(text) {
    const lower = text.toLowerCase();
    return RENTAL_KEYWORDS.some((kw) => lower.includes(kw.toLowerCase())) && extractPrice(text);
  }

  function extractFromArticle(article) {
    const text = article.innerText || "";
    if (!isRentalPost(text)) return null;

    const img = article.querySelector("img[src*='scontent']");
    const links = Array.from(article.querySelectorAll("a[href]"));
    const postLink = links.find((a) => /\/(groups|permalink|posts)\//.test(a.href));
    const url = postLink ? postLink.href : location.href;

    const authorEl = article.querySelector("h3 a, h4 a, strong a, [role='link'] strong");
    const contactName = authorEl ? authorEl.innerText.trim() : "";

    // First non-empty line as title
    const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
    const title = lines[0]?.slice(0, 120) || "Group Rental Post";

    return {
      title,
      description: text.slice(0, 600),
      price: extractPrice(text),
      rooms: extractRooms(text),
      floor: extractFloor(text),
      size_sqm: extractSqm(text),
      city: "",
      neighborhood: "",
      address: "",
      image_url: img ? img.src : null,
      url,
      contact_name: contactName,
    };
  }

  // ── Scroll page to load more posts ───────────────────────────────────────

  async function scrollAndCollect() {
    const seen = new Set();
    const results = [];

    function collect() {
      const articles = document.querySelectorAll('[role="article"]');
      articles.forEach((article) => {
        const key = article.innerText?.slice(0, 80);
        if (!key || seen.has(key)) return;
        seen.add(key);
        const listing = extractFromArticle(article);
        if (listing) results.push(listing);
      });
    }

    collect(); // initial

    for (let i = 0; i < SCROLL_STEPS; i++) {
      window.scrollBy(0, window.innerHeight * 1.5);
      await new Promise((r) => setTimeout(r, SCROLL_DELAY));
      collect();
    }

    // Scroll back to top
    window.scrollTo(0, 0);
    return results;
  }

  const listings = await scrollAndCollect();
  return listings; // returned as executeScript result
})();
