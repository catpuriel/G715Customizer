"""Physical layout & 0x8081 LED zone map for the Logitech G715 TKL keyboard.

Every key / media button / perimeter underglow LED / logo LED has:
  - zone_id: 0x8081 PerKeyLighting v2 zone byte (probed from real hardware)
  - label: Human-readable display label
  - x, y, w, h: Coordinates in standard keycap units (1u = 1.0)
  - group: "keys", "modifiers", "function", "nav", "arrows", "media", "perimeter", "logo"
"""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class LedCell:
    zone_id: int
    label: str
    x: float
    y: float
    w: float
    h: float
    group: str
    shape: str = "key"  # "key", "pill", "circle", "perimeter", "logo"


def build_g715_layout() -> list[LedCell]:
    """Return the complete interactive visual layout for the Logitech G715 ANSI TKL + 16-LED underglow."""
    cells: list[LedCell] = []

    # --- Top Hardware Controls Row (y = 0.0) ---
    # G715 has Lightspeed, Bluetooth, Game Mode, Brightness on left-center, and Media keys on right
    cells.extend([
        LedCell(0xD2, "G", 0.3, 0.05, 0.85, 0.65, "logo", shape="logo"),
        LedCell(0x96, "LS", 3.2, 0.1, 0.9, 0.55, "media", shape="pill"),
        LedCell(0x98, "BT", 4.3, 0.1, 0.9, 0.55, "media", shape="pill"),
        LedCell(0x9A, "GAME", 5.6, 0.1, 0.95, 0.55, "media", shape="pill"),
        LedCell(0x99, "BRI", 6.75, 0.1, 0.9, 0.55, "media", shape="pill"),
        LedCell(0x9B, "MUTE", 15.2, 0.1, 0.9, 0.55, "media", shape="pill"),
    ])

    # --- Row 0: Esc + F1-F12 + PrtSc / ScrLk / Pause (y = 1.1) ---
    y0 = 1.1
    cells.append(LedCell(0x26, "Esc", 0.0, y0, 1.0, 1.0, "function"))
    for i, (zid, lbl) in enumerate([
        (0x37, "F1"), (0x38, "F2"), (0x39, "F3"), (0x3A, "F4"),
    ]):
        cells.append(LedCell(zid, lbl, 2.0 + i * 1.0, y0, 1.0, 1.0, "function"))
    for i, (zid, lbl) in enumerate([
        (0x3B, "F5"), (0x3C, "F6"), (0x3D, "F7"), (0x3E, "F8"),
    ]):
        cells.append(LedCell(zid, lbl, 6.5 + i * 1.0, y0, 1.0, 1.0, "function"))
    for i, (zid, lbl) in enumerate([
        (0x3F, "F9"), (0x40, "F10"), (0x41, "F11"), (0x42, "F12"),
    ]):
        cells.append(LedCell(zid, lbl, 11.0 + i * 1.0, y0, 1.0, 1.0, "function"))

    cells.extend([
        LedCell(0x43, "PrtSc", 15.25, y0, 1.0, 1.0, "nav"),
        LedCell(0x44, "ScrLk", 16.25, y0, 1.0, 1.0, "nav"),
        LedCell(0x45, "Pause", 17.25, y0, 1.0, 1.0, "nav"),
    ])

    # --- Row 1: Number Row (y = 2.35) ---
    y1 = 2.35
    row1 = [
        (0x32, "`", 1.0), (0x1B, "1", 1.0), (0x1C, "2", 1.0), (0x1D, "3", 1.0),
        (0x1E, "4", 1.0), (0x1F, "5", 1.0), (0x20, "6", 1.0), (0x21, "7", 1.0),
        (0x22, "8", 1.0), (0x23, "9", 1.0), (0x24, "0", 1.0), (0x2A, "-", 1.0),
        (0x2B, "=", 1.0), (0x27, "Bksp", 2.0),
    ]
    x = 0.0
    for zid, lbl, w in row1:
        grp = "modifiers" if lbl == "Bksp" else "keys"
        cells.append(LedCell(zid, lbl, x, y1, w, 1.0, grp))
        x += w
    cells.extend([
        LedCell(0x46, "Ins", 15.25, y1, 1.0, 1.0, "nav"),
        LedCell(0x47, "Home", 16.25, y1, 1.0, 1.0, "nav"),
        LedCell(0x48, "PgUp", 17.25, y1, 1.0, 1.0, "nav"),
    ])

    # --- Row 2: QWERTY Row (y = 3.35) ---
    y2 = 3.35
    row2 = [
        (0x28, "Tab", 1.5), (0x11, "Q", 1.0), (0x17, "W", 1.0), (0x05, "E", 1.0),
        (0x12, "R", 1.0), (0x14, "T", 1.0), (0x19, "Y", 1.0), (0x15, "U", 1.0),
        (0x09, "I", 1.0), (0x0F, "O", 1.0), (0x10, "P", 1.0), (0x2C, "[", 1.0),
        (0x2D, "]", 1.0), (0x2F, "\\", 1.5),
    ]
    x = 0.0
    for zid, lbl, w in row2:
        grp = "modifiers" if lbl == "Tab" else "keys"
        cells.append(LedCell(zid, lbl, x, y2, w, 1.0, grp))
        x += w
    cells.extend([
        LedCell(0x49, "Del", 15.25, y2, 1.0, 1.0, "nav"),
        LedCell(0x4A, "End", 16.25, y2, 1.0, 1.0, "nav"),
        LedCell(0x4B, "PgDn", 17.25, y2, 1.0, 1.0, "nav"),
    ])

    # --- Row 3: ASDF Row (y = 4.35) ---
    y3 = 4.35
    row3 = [
        (0x36, "Caps", 1.75), (0x01, "A", 1.0), (0x13, "S", 1.0), (0x04, "D", 1.0),
        (0x06, "F", 1.0), (0x07, "G", 1.0), (0x08, "H", 1.0), (0x0A, "J", 1.0),
        (0x0B, "K", 1.0), (0x0C, "L", 1.0), (0x30, ";", 1.0), (0x31, "'", 1.0),
        (0x25, "Enter", 2.25),
    ]
    x = 0.0
    for zid, lbl, w in row3:
        grp = "modifiers" if lbl in ("Caps", "Enter") else "keys"
        cells.append(LedCell(zid, lbl, x, y3, w, 1.0, grp))
        x += w

    # --- Row 4: ZXCV Row (y = 5.35) ---
    y4 = 5.35
    row4 = [
        (0x69, "LShift", 2.25), (0x1A, "Z", 1.0), (0x18, "X", 1.0), (0x03, "C", 1.0),
        (0x16, "V", 1.0), (0x02, "B", 1.0), (0x0E, "N", 1.0), (0x0D, "M", 1.0),
        (0x33, ",", 1.0), (0x34, ".", 1.0), (0x35, "/", 1.0), (0x6D, "RShift", 2.75),
    ]
    x = 0.0
    for zid, lbl, w in row4:
        grp = "modifiers" if "Shift" in lbl else "keys"
        cells.append(LedCell(zid, lbl, x, y4, w, 1.0, grp))
        x += w
    cells.append(LedCell(0x4F, "Up", 16.25, y4, 1.0, 1.0, "arrows"))

    # --- Row 5: Bottom Modifiers + Space + Arrows (y = 6.35) ---
    y5 = 6.35
    row5 = [
        (0x68, "LCtrl", 1.25), (0x6B, "Super", 1.25), (0x6A, "LAlt", 1.25),
        (0x29, "Space", 6.25),
        (0x6E, "RAlt", 1.25), (0x6F, "Fn", 1.25), (0x62, "Menu", 1.25), (0x6C, "RCtrl", 1.25),
    ]
    x = 0.0
    for zid, lbl, w in row5:
        cells.append(LedCell(zid, lbl, x, y5, w, 1.0, "modifiers"))
        x += w
    cells.extend([
        LedCell(0x4D, "Left", 15.25, y5, 1.0, 1.0, "arrows"),
        LedCell(0x4E, "Down", 16.25, y5, 1.0, 1.0, "arrows"),
        LedCell(0x4C, "Right", 17.25, y5, 1.0, 1.0, "arrows"),
    ])

    # --- 16 Perimeter / Underglow LEDs (0xA0..0xAF) surrounding the G715 chassis ---
    # Arranged clockwise around the keyboard perimeter for intuitive visual painting:
    # Bottom edge (6), Left edge (2), Top edge (6), Right edge (2) = 16 LEDs
    perimeter_positions = [
        # Bottom edge left-to-right (0xA0..0xA5)
        (0xA0, "U1",  1.0,  7.75, 2.2, 0.42),
        (0xA1, "U2",  3.6,  7.75, 2.2, 0.42),
        (0xA2, "U3",  6.2,  7.75, 2.2, 0.42),
        (0xA3, "U4",  8.8,  7.75, 2.2, 0.42),
        (0xA4, "U5",  11.4, 7.75, 2.2, 0.42),
        (0xA5, "U6",  14.0, 7.75, 2.2, 0.42),
        # Right edge bottom-to-top (0xA6..0xA7)
        (0xA6, "U7",  18.55, 4.7, 0.42, 2.3),
        (0xA7, "U8",  18.55, 1.6, 0.42, 2.3),
        # Top edge right-to-left (0xA8..0xAD)
        (0xA8, "U9",  14.0, -0.7, 2.2, 0.42),
        (0xA9, "U10", 11.4, -0.7, 2.2, 0.42),
        (0xAA, "U11", 8.8,  -0.7, 2.2, 0.42),
        (0xAB, "U12", 6.2,  -0.7, 2.2, 0.42),
        (0xAC, "U13", 3.6,  -0.7, 2.2, 0.42),
        (0xAD, "U14", 1.0,  -0.7, 2.2, 0.42),
        # Left edge top-to-bottom (0xAE..0xAF)
        (0xAE, "U15", -0.72, 1.6, 0.42, 2.3),
        (0xAF, "U16", -0.72, 4.7, 0.42, 2.3),
    ]
    for zid, lbl, px, py, pw, ph in perimeter_positions:
        cells.append(LedCell(zid, lbl, px, py, pw, ph, "perimeter", shape="perimeter"))

    return cells


G715_LAYOUT = build_g715_layout()
ZONE_ID_TO_CELL = {c.zone_id: c for c in G715_LAYOUT}
KEY_ZONE_IDS = [c.zone_id for c in G715_LAYOUT if c.group != "perimeter"]
PERIMETER_ZONE_IDS = [c.zone_id for c in G715_LAYOUT if c.group == "perimeter"]
ALL_LAYOUT_ZONE_IDS = [c.zone_id for c in G715_LAYOUT]
WASD_ZONE_IDS = [0x17, 0x01, 0x13, 0x04]  # W, A, S, D
ARROW_ZONE_IDS = [0x4F, 0x4D, 0x4E, 0x4C]  # Up, Left, Down, Right
