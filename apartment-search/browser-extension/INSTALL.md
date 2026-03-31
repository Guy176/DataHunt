# Browser Extension — Install Guide

## Chrome / Edge (Recommended)

1. Open Chrome and go to `chrome://extensions`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked**
4. Select the `browser-extension/` folder from this project
5. The extension icon (house) appears in your toolbar

## Firefox

1. Open `about:debugging#/runtime/this-firefox`
2. Click **Load Temporary Add-on**
3. Select the `manifest.json` file inside `browser-extension/`
4. Note: Firefox requires reloading after each browser restart (use the signed version for permanent install)

## Generate Icons (optional)

The extension ships without PNG icons. To generate them:

```bash
cd browser-extension/icons
pip install cairosvg
python generate_icons.py
```

Or paste the SVG from `generate_icons.py` into any online SVG→PNG converter for sizes 16, 48, 128.

---

## How to Use

### Save a Single Listing (Marketplace or Group Post)

1. Browse to a **Facebook Marketplace** listing page
2. A blue **"Save Listing"** button appears in the bottom-right corner
3. Click it — the popup opens with auto-extracted data
4. Review / edit the fields, then click **Save**

Or on **group pages**: a small **"💾 Save to Apartment Search"** button appears
below rental posts in the feed.

### Scan All Open Group Tabs at Once

1. Open all the Facebook rental groups you're interested in as separate Chrome tabs
2. Click the extension icon in the toolbar
3. Switch to the **"Scan All Tabs"** tab
4. Click **"Scan All Facebook Group Tabs"**
5. The extension scrolls through every group tab and saves all rental posts it finds
6. Duplicates are automatically skipped

---

## Settings

Click the ⚙️ gear icon in the extension popup to open Settings.

| Setting | Default | Description |
|---------|---------|-------------|
| Backend URL | `http://localhost:8000` | Where your apartment search backend is running |

Use **Test Connection** to verify the backend is reachable before scanning.

---

## Permissions Required

| Permission | Why |
|------------|-----|
| `tabs` | Read URLs of open tabs to find Facebook group tabs |
| `scripting` | Inject the scanner script into group tabs |
| `storage` | Save your API URL setting |
| `host_permissions: facebook.com` | Read page content for extraction |
| `host_permissions: localhost` | POST listings to your local backend |
