"""
Run this once to generate icon PNGs from the SVG.
Requires: pip install cairosvg
"""
import cairosvg, os

SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">
  <rect width="48" height="48" rx="12" fill="#2563eb"/>
  <path d="M8 26 L24 10 L40 26 L40 40 H28 V30 H20 V40 H8 Z"
        fill="none" stroke="white" stroke-width="3"
        stroke-linejoin="round" stroke-linecap="round"/>
</svg>"""

os.makedirs(".", exist_ok=True)
for size in [16, 48, 128]:
    cairosvg.svg2png(
        bytestring=SVG.encode(),
        write_to=f"icon{size}.png",
        output_width=size,
        output_height=size,
    )
    print(f"Generated icon{size}.png")
