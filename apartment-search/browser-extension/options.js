function $(id) { return document.getElementById(id); }

// Load saved settings
chrome.storage.sync.get({ apiUrl: "http://localhost:8000" }, ({ apiUrl }) => {
  $("api-url").value = apiUrl;
});

// Save
$("save-btn").addEventListener("click", () => {
  const apiUrl = $("api-url").value.trim().replace(/\/$/, "");
  if (!apiUrl) return showMsg("Please enter a URL.", "error");
  chrome.storage.sync.set({ apiUrl }, () => {
    showMsg("Settings saved!", "success");
  });
});

// Test connection
$("test-btn").addEventListener("click", async () => {
  const url = $("api-url").value.trim().replace(/\/$/, "");
  showMsg("Testing…", "");
  try {
    const resp = await fetch(`${url}/api/health`, { signal: AbortSignal.timeout(5000) });
    if (resp.ok) {
      const data = await resp.json();
      showMsg(`Connected! Backend v${data.version || "?"}`, "success");
    } else {
      showMsg(`Error: HTTP ${resp.status}`, "error");
    }
  } catch (err) {
    showMsg(`Cannot reach backend: ${err.message}`, "error");
  }
});

function showMsg(text, type) {
  const el = $("msg");
  el.textContent = text;
  el.className = `msg${type ? " " + type : ""}`;
  el.classList.remove("hidden");
}
