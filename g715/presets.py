"""Preset management, built-in Aurora/cyberpunk/pastel palettes, and flash backups."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from .layout import ALL_LAYOUT_ZONE_IDS, ARROW_ZONE_IDS, G715_LAYOUT, KEY_ZONE_IDS, PERIMETER_ZONE_IDS, WASD_ZONE_IDS
from .protocol import (
    EFFECT_AURORA_PLAYFUL,
    EFFECT_AURORA_PLAYFUL_DIM,
    EFFECT_BREATHE,
    EFFECT_CYCLE,
    EFFECT_RIPPLE,
    EFFECT_STATIC,
    EFFECT_WAVE,
    LedEffect,
    dim_color,
    format_hex_color,
    parse_hex_color,
)

DATA_DIR = Path.home() / ".local" / "share" / "g715-customizer"
BACKUPS_DIR = DATA_DIR / "backups"
ONBOARD_PRESETS_FILE = DATA_DIR / "onboard_presets.json"
PERKEY_PRESETS_FILE = DATA_DIR / "perkey_presets.json"

# Curated built-in onboard presets tailored for the Logitech G715 Aurora Collection
BUILTIN_ONBOARD_PRESETS: dict[str, dict[str, Any]] = {
    "Aurora Pink & Cyan": {
        "keys_active": LedEffect(EFFECT_STATIC, color=0xFF73B9).to_dict(),
        "perimeter_active": LedEffect(EFFECT_STATIC, color=0x6BE5F5).to_dict(),
        "keys_dim": LedEffect(EFFECT_STATIC, color=dim_color(0xFF73B9, 0.45)).to_dict(),
        "perimeter_dim": LedEffect(EFFECT_STATIC, color=dim_color(0x6BE5F5, 0.45)).to_dict(),
    },
    "Electric Magenta": {
        "keys_active": LedEffect(EFFECT_STATIC, color=0xF552FF).to_dict(),
        "perimeter_active": LedEffect(EFFECT_STATIC, color=0xF552FF).to_dict(),
        "keys_dim": LedEffect(EFFECT_STATIC, color=0x7A297F).to_dict(),
        "perimeter_dim": LedEffect(EFFECT_STATIC, color=0x7A297F).to_dict(),
    },
    "Cyberpunk Neon": {
        "keys_active": LedEffect(EFFECT_STATIC, color=0x00F0FF).to_dict(),
        "perimeter_active": LedEffect(EFFECT_STATIC, color=0xFF1E8E).to_dict(),
        "keys_dim": LedEffect(EFFECT_STATIC, color=dim_color(0x00F0FF, 0.4)).to_dict(),
        "perimeter_dim": LedEffect(EFFECT_STATIC, color=dim_color(0xFF1E8E, 0.4)).to_dict(),
    },
    "Lavender Cloud": {
        "keys_active": LedEffect(EFFECT_STATIC, color=0xC8A2FF).to_dict(),
        "perimeter_active": LedEffect(EFFECT_STATIC, color=0x90E0FF).to_dict(),
        "keys_dim": LedEffect(EFFECT_STATIC, color=dim_color(0xC8A2FF, 0.45)).to_dict(),
        "perimeter_dim": LedEffect(EFFECT_STATIC, color=dim_color(0x90E0FF, 0.45)).to_dict(),
    },
    "Warm Sunset": {
        "keys_active": LedEffect(EFFECT_STATIC, color=0xFFB36B).to_dict(),
        "perimeter_active": LedEffect(EFFECT_STATIC, color=0xFF5E7E).to_dict(),
        "keys_dim": LedEffect(EFFECT_STATIC, color=dim_color(0xFFB36B, 0.4)).to_dict(),
        "perimeter_dim": LedEffect(EFFECT_STATIC, color=dim_color(0xFF5E7E, 0.4)).to_dict(),
    },
    "Mint Matcha": {
        "keys_active": LedEffect(EFFECT_STATIC, color=0x7CFFB2).to_dict(),
        "perimeter_active": LedEffect(EFFECT_STATIC, color=0xD4FFE4).to_dict(),
        "keys_dim": LedEffect(EFFECT_STATIC, color=dim_color(0x7CFFB2, 0.4)).to_dict(),
        "perimeter_dim": LedEffect(EFFECT_STATIC, color=dim_color(0xD4FFE4, 0.4)).to_dict(),
    },
    "Clean Warm White": {
        "keys_active": LedEffect(EFFECT_STATIC, color=0xFFE6C8).to_dict(),
        "perimeter_active": LedEffect(EFFECT_STATIC, color=0xFFF2E2).to_dict(),
        "keys_dim": LedEffect(EFFECT_STATIC, color=dim_color(0xFFE6C8, 0.35)).to_dict(),
        "perimeter_dim": LedEffect(EFFECT_STATIC, color=dim_color(0xFFF2E2, 0.35)).to_dict(),
    },
    "Rainbow Wave": {
        "keys_active": LedEffect(EFFECT_WAVE, saturation=255, period=4500, intensity=100, direction=1).to_dict(),
        "perimeter_active": LedEffect(EFFECT_WAVE, saturation=255, period=4500, intensity=100, direction=1).to_dict(),
        "keys_dim": LedEffect(EFFECT_WAVE, saturation=255, period=6000, intensity=45, direction=1).to_dict(),
        "perimeter_dim": LedEffect(EFFECT_WAVE, saturation=255, period=6000, intensity=45, direction=1).to_dict(),
    },
    "Pastel Color Cycle": {
        "keys_active": LedEffect(EFFECT_CYCLE, saturation=180, period=8000, intensity=100).to_dict(),
        "perimeter_active": LedEffect(EFFECT_CYCLE, saturation=210, period=8000, intensity=100).to_dict(),
        "keys_dim": LedEffect(EFFECT_CYCLE, saturation=180, period=10000, intensity=45).to_dict(),
        "perimeter_dim": LedEffect(EFFECT_CYCLE, saturation=210, period=10000, intensity=45).to_dict(),
    },
    "Pink Breathing + Cyan Glow": {
        "keys_active": LedEffect(EFFECT_BREATHE, color=0xFF55BB, period=4500, intensity=100).to_dict(),
        "perimeter_active": LedEffect(EFFECT_STATIC, color=0x55E5FF).to_dict(),
        "keys_dim": LedEffect(EFFECT_STATIC, color=dim_color(0xFF55BB, 0.35)).to_dict(),
        "perimeter_dim": LedEffect(EFFECT_STATIC, color=dim_color(0x55E5FF, 0.35)).to_dict(),
    },
    "Echo Ripple Pink": {
        "keys_active": LedEffect(EFFECT_RIPPLE, color=0xFF55CC, saturation=255, period=22).to_dict(),
        "perimeter_active": LedEffect(EFFECT_STATIC, color=0x5B2C8A).to_dict(),
        "keys_dim": LedEffect(EFFECT_STATIC, color=0x33123A).to_dict(),
        "perimeter_dim": LedEffect(EFFECT_STATIC, color=0x2B1545).to_dict(),
    },
    "Aurora Playful (Factory)": {
        "keys_active": LedEffect(EFFECT_BREATHE, color=0x00FF00, period=4352, intensity=100).to_dict(),
        "perimeter_active": LedEffect(EFFECT_AURORA_PLAYFUL).to_dict(),
        "keys_dim": LedEffect(EFFECT_BREATHE, color=0x0000FF, period=4352, intensity=100).to_dict(),
        "perimeter_dim": LedEffect(EFFECT_AURORA_PLAYFUL_DIM).to_dict(),
    },
}


def _lerp_color(c1: int, c2: int, t: float) -> int:
    t = max(0.0, min(1.0, t))
    r = int(((c1 >> 16) & 0xFF) * (1 - t) + ((c2 >> 16) & 0xFF) * t)
    g = int(((c1 >> 8) & 0xFF) * (1 - t) + ((c2 >> 8) & 0xFF) * t)
    b = int((c1 & 0xFF) * (1 - t) + (c2 & 0xFF) * t)
    return (r << 16) | (g << 8) | b


def generate_gradient_layout(left_color: int, right_color: int, perim_left: int | None = None, perim_right: int | None = None) -> dict[int, int]:
    """Generate a smooth horizontal gradient across all G715 keys & perimeter LEDs."""
    pl = left_color if perim_left is None else perim_left
    pr = right_color if perim_right is None else perim_right
    min_x = min(c.x for c in G715_LAYOUT)
    max_x = max(c.x + c.w for c in G715_LAYOUT)
    span = max(0.1, max_x - min_x)
    out: dict[int, int] = {}
    for cell in G715_LAYOUT:
        cx = cell.x + cell.w * 0.5
        t = (cx - min_x) / span
        if cell.group == "perimeter":
            out[cell.zone_id] = _lerp_color(pl, pr, t)
        else:
            out[cell.zone_id] = _lerp_color(left_color, right_color, t)
    return out


def build_builtin_perkey_presets() -> dict[str, dict[int, int]]:
    presets: dict[str, dict[int, int]] = {}

    # 1. Aurora Gradient (Pink -> Lavender -> Cyan)
    aurora: dict[int, int] = {}
    for cell in G715_LAYOUT:
        t = max(0.0, min(1.0, (cell.x + cell.w * 0.5 + 0.7) / 19.7))
        if t < 0.5:
            col = _lerp_color(0xFF66B2, 0xB388FF, t * 2.0)
        else:
            col = _lerp_color(0xB388FF, 0x64EEFF, (t - 0.5) * 2.0)
        aurora[cell.zone_id] = col
    presets["Aurora Gradient"] = aurora

    # 2. Gaming WASD Highlight
    gaming = {z: 0x3B1D6E for z in KEY_ZONE_IDS}
    for z in PERIMETER_ZONE_IDS:
        gaming[z] = 0x00E5FF
    for z in WASD_ZONE_IDS + ARROW_ZONE_IDS:
        gaming[z] = 0xFF2E93
    gaming[0x26] = 0xFF3344  # Esc
    gaming[0x29] = 0x00E5FF  # Space
    gaming[0xD2] = 0xFF2E93  # Logo
    presets["Gaming WASD"] = gaming

    # 3. Cotton Candy Split
    presets["Cotton Candy"] = generate_gradient_layout(0xFF77C8, 0x70E8FF, 0x70E8FF, 0xFF77C8)

    # 4. Sunset Horizon
    presets["Sunset Horizon"] = generate_gradient_layout(0xFF4D6D, 0xFFBE0B, 0x8338EC, 0xFF006E)

    # 5. Synthwave Grid
    synth: dict[int, int] = {}
    for cell in G715_LAYOUT:
        if cell.group == "perimeter":
            synth[cell.zone_id] = 0xFF00AA
        elif cell.group in ("modifiers", "function", "media", "logo"):
            synth[cell.zone_id] = 0x9B26FF
        elif cell.group in ("nav", "arrows"):
            synth[cell.zone_id] = 0xFF3399
        else:
            synth[cell.zone_id] = 0x00F5FF
    presets["Synthwave Grid"] = synth

    # 6. Clean Mint & White
    mint: dict[int, int] = {}
    for cell in G715_LAYOUT:
        if cell.group == "perimeter":
            mint[cell.zone_id] = 0x66FFBA
        elif cell.group == "modifiers":
            mint[cell.zone_id] = 0x80FFD4
        else:
            mint[cell.zone_id] = 0xFFF5EB
    presets["Mint & Cream"] = mint

    return presets


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)


def load_user_onboard_presets() -> dict[str, dict[str, Any]]:
    ensure_data_dirs()
    if not ONBOARD_PRESETS_FILE.exists():
        return {}
    try:
        return json.loads(ONBOARD_PRESETS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_user_onboard_preset(name: str, preset: dict[str, Any]) -> None:
    ensure_data_dirs()
    data = load_user_onboard_presets()
    data[name] = preset
    ONBOARD_PRESETS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def delete_user_onboard_preset(name: str) -> bool:
    ensure_data_dirs()
    data = load_user_onboard_presets()
    if name in data:
        del data[name]
        ONBOARD_PRESETS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True
    return False


def load_user_perkey_presets() -> dict[str, dict[int, int]]:
    ensure_data_dirs()
    if not PERKEY_PRESETS_FILE.exists():
        return {}
    try:
        raw = json.loads(PERKEY_PRESETS_FILE.read_text(encoding="utf-8"))
        out: dict[str, dict[int, int]] = {}
        for pname, zmap in raw.items():
            out[pname] = {
                int(k, 0): (parse_hex_color(v) if isinstance(v, str) else int(v))
                for k, v in zmap.items()
            }
        return out
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def save_user_perkey_preset(name: str, zone_colors: dict[int, int]) -> None:
    ensure_data_dirs()
    raw: dict[str, dict[str, str]] = {}
    if PERKEY_PRESETS_FILE.exists():
        try:
            raw = json.loads(PERKEY_PRESETS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
    raw[name] = {f"0x{z:02x}": format_hex_color(c) for z, c in sorted(zone_colors.items())}
    PERKEY_PRESETS_FILE.write_text(json.dumps(raw, indent=2), encoding="utf-8")


def delete_user_perkey_preset(name: str) -> bool:
    ensure_data_dirs()
    if not PERKEY_PRESETS_FILE.exists():
        return False
    try:
        raw = json.loads(PERKEY_PRESETS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if name in raw:
        del raw[name]
        PERKEY_PRESETS_FILE.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        return True
    return False


def save_backup(sectors: dict[str, str], label: str = "backup") -> Path:
    ensure_data_dirs()
    safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in label).strip("_") or "backup"
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = BACKUPS_DIR / f"{ts}_{safe_label}.json"
    payload = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "label": label,
        "sectors": sectors,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def list_backups() -> list[Path]:
    ensure_data_dirs()
    return sorted(BACKUPS_DIR.glob("*.json"), reverse=True)


def load_backup(path: str | os.PathLike) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
