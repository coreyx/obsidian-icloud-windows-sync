"""
Tray icon images per state (Requirement 1.3).

Generates simple programmatic icons via Pillow rather than shipping
hand-designed artwork, since none exists in this repo -- swap in a real
.ico under assets/ later if desired; icon_for()'s return type (a PIL
Image) is exactly what pystray.Icon expects either way.
"""

from typing import Dict

from PIL import Image, ImageDraw

_SIZE = 64
_COLORS = {
    "idle": (128, 128, 128, 255),   # gray
    "daemon": (46, 160, 67, 255),   # green
    "once": (33, 133, 208, 255),    # blue
}
_TOOLTIPS = {
    "idle": "obsidian-sync — Idle",
    "daemon": "obsidian-sync — Running",
    "once": "obsidian-sync — Running once...",
}

_cache: Dict[str, "Image.Image"] = {}


def _make_icon(color) -> "Image.Image":
    img = Image.new("RGBA", (_SIZE, _SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = 6
    draw.ellipse([margin, margin, _SIZE - margin, _SIZE - margin], fill=color)
    return img


def icon_for(mode: str) -> "Image.Image":
    """mode: 'idle' | 'daemon' | 'once'"""
    if mode not in _cache:
        _cache[mode] = _make_icon(_COLORS.get(mode, _COLORS["idle"]))
    return _cache[mode]


def tooltip_for(mode: str) -> str:
    return _TOOLTIPS.get(mode, "obsidian-sync")
