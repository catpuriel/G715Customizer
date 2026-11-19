"""Logitech G715 HID++ 2.0/4.2 protocol controller.

Implements:
  - 0x8100 Onboard Profiles (read/write 255-byte flash sectors with CRC16-CCITT, mode & active profile)
  - 0x8071 RGB Effects (live zone effects, SW control takeover/release, NvConfig startup/shutdown animations)
  - 0x8081 Per-Key Lighting v2 (117 addressable LEDs: keys, media buttons, 16 perimeter LEDs, G logo)
  - 0x8040 Brightness Control
  - 0x8060 Report Rate
  - 0x1004 Unified Battery
"""

from __future__ import annotations

import dataclasses
import struct
import time
from typing import Optional

from .hidpp import DeviceCandidate, HidppError, HidppTransport, discover_g715_devices

# HID++ Feature IDs verified on Logitech G715 (046d:c347)
FEAT_UNIFIED_BATTERY = 0x1004
FEAT_BRIGHTNESS = 0x8040
FEAT_REPORT_RATE = 0x8060
FEAT_RGB_EFFECTS = 0x8071
FEAT_PER_KEY_V2 = 0x8081
FEAT_ONBOARD_PROFILES = 0x8100

# 0x8071 SW control payloads
SW_ACTIVE = bytes([0x01, 0x03, 0x04])   # mode=3, flags=FLAG_NVCONFIG
SW_RELEASE = bytes([0x01, 0x00, 0x00])  # mode=0, flags=0

# Effect IDs supported by G715 (verified from 0x8071 + ROM 0x0101)
EFFECT_OFF = 0x00
EFFECT_STATIC = 0x01
EFFECT_BREATHE = 0x0A
EFFECT_CYCLE = 0x15
EFFECT_WAVE = 0x16
EFFECT_RIPPLE = 0x17
EFFECT_AURORA_PLAYFUL = 0x18
EFFECT_AURORA_PLAYFUL_DIM = 0x19

EFFECT_NAMES = {
    EFFECT_OFF: "Off",
    EFFECT_STATIC: "Static Color",
    EFFECT_BREATHE: "Breathing",
    EFFECT_CYCLE: "Color Cycle",
    EFFECT_WAVE: "Color Wave",
    EFFECT_RIPPLE: "Echo Press (Ripple)",
    EFFECT_AURORA_PLAYFUL: "Aurora Playful (Factory)",
    EFFECT_AURORA_PLAYFUL_DIM: "Aurora Playful Dim (Factory)",
}

WAVE_DIRECTIONS = {
    0: "Cycle",
    1: "Right",
    2: "Down",
    3: "Center Out",
    4: "In",
    5: "Out",
    6: "Left",
    7: "Up",
    8: "Center In",
}

# Common USB HID keyboard keycodes for F1-F12 remapping
USB_HID_KEYS: dict[int, str] = {
    0x00: "None",
    0x04: "A", 0x05: "B", 0x06: "C", 0x07: "D", 0x08: "E", 0x09: "F",
    0x0A: "G", 0x0B: "H", 0x0C: "I", 0x0D: "J", 0x0E: "K", 0x0F: "L",
    0x10: "M", 0x11: "N", 0x12: "O", 0x13: "P", 0x14: "Q", 0x15: "R",
    0x16: "S", 0x17: "T", 0x18: "U", 0x19: "V", 0x1A: "W", 0x1B: "X",
    0x1C: "Y", 0x1D: "Z",
    0x1E: "1", 0x1F: "2", 0x20: "3", 0x21: "4", 0x22: "5",
    0x23: "6", 0x24: "7", 0x25: "8", 0x26: "9", 0x27: "0",
    0x28: "Enter", 0x29: "Escape", 0x2A: "Backspace", 0x2B: "Tab", 0x2C: "Space",
    0x3A: "F1", 0x3B: "F2", 0x3C: "F3", 0x3D: "F4", 0x3E: "F5", 0x3F: "F6",
    0x40: "F7", 0x41: "F8", 0x42: "F9", 0x43: "F10", 0x44: "F11", 0x45: "F12",
    0x46: "Print Screen", 0x47: "Scroll Lock", 0x48: "Pause",
    0x49: "Insert", 0x4A: "Home", 0x4B: "Page Up", 0x4C: "Delete",
    0x4D: "End", 0x4E: "Page Down",
    0x4F: "Right", 0x50: "Left", 0x51: "Down", 0x52: "Up",
    0x68: "F13", 0x69: "F14", 0x6A: "F15", 0x6B: "F16", 0x6C: "F17", 0x6D: "F18",
    0x6E: "F19", 0x6F: "F20", 0x70: "F21", 0x71: "F22", 0x72: "F23", 0x73: "F24",
}

CONSUMER_KEYS: dict[int, str] = {
    0x00B5: "Next Track",
    0x00B6: "Previous Track",
    0x00B7: "Stop",
    0x00CD: "Play / Pause",
    0x00E2: "Mute",
    0x00E9: "Volume Up",
    0x00EA: "Volume Down",
    0x0183: "Media Player",
    0x018A: "Email",
    0x0192: "Calculator",
    0x0194: "File Browser",
    0x0221: "Search",
    0x0223: "Browser Home",
    0x0224: "Browser Back",
    0x0225: "Browser Forward",
}

MODIFIER_BITS = [
    (0x01, "LCtrl"),
    (0x02, "LShift"),
    (0x04, "LAlt"),
    (0x08, "LSuper"),
    (0x10, "RCtrl"),
    (0x20, "RShift"),
    (0x40, "RAlt"),
    (0x80, "RSuper"),
]


def crc16_ccitt(data: bytes) -> int:
    """Compute CRC-16/CCITT-FALSE (init=0xFFFF, poly=0x1021) used by Logitech 0x8100 sectors."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def parse_hex_color(value: str) -> int:
    """Parse '#RRGGBB' or 'RRGGBB' into a 24-bit int."""
    s = value.strip().lstrip("#")
    if s.lower().startswith("0x"):
        s = s[2:]
    if len(s) != 6:
        raise ValueError(f"Expected 6-digit hex color, got {value!r}")
    return int(s, 16) & 0xFFFFFF


def format_hex_color(color: int) -> str:
    return f"#{color & 0xFFFFFF:06X}"


def dim_color(color: int, factor: float = 0.5) -> int:
    """Scale an RGB color by factor (0.0..1.0) for power-save / dim state."""
    factor = max(0.0, min(1.0, factor))
    r = int(((color >> 16) & 0xFF) * factor)
    g = int(((color >> 8) & 0xFF) * factor)
    b = int((color & 0xFF) * factor)
    return (r << 16) | (g << 8) | b


@dataclasses.dataclass
class LedEffect:
    """11-byte LED effect specification used in both 0x8100 onboard sectors and 0x8071 live updates."""

    effect_id: int = EFFECT_STATIC
    color: int = 0xF552FF
    period: int = 5000        # ms for Breathe/Cycle/Wave; 2..200 for Ripple
    intensity: int = 100      # 0..100
    saturation: int = 255     # 0..255
    direction: int = 1        # 0..8 for Wave
    ramp: int = 2             # 0..2 for Static (G HUB defaults to 2)
    form: int = 1             # 1=Sine for Breathe
    raw_bytes: Optional[bytes] = None  # Preserved for factory/unknown effect IDs

    def to_bytes(self) -> bytes:
        """Serialize to the exact 11-byte onboard/wire representation."""
        eid = self.effect_id & 0xFF
        if eid in (EFFECT_AURORA_PLAYFUL, EFFECT_AURORA_PLAYFUL_DIM):
            if self.raw_bytes and len(self.raw_bytes) == 11 and self.raw_bytes[0] == eid:
                return self.raw_bytes
            return bytes([eid]) + b"\x00" * 10
        if eid not in EFFECT_NAMES and self.raw_bytes and len(self.raw_bytes) == 11:
            return self.raw_bytes

        p = bytearray(10)
        r = (self.color >> 16) & 0xFF
        g = (self.color >> 8) & 0xFF
        b = self.color & 0xFF

        if eid == EFFECT_OFF:
            pass
        elif eid == EFFECT_STATIC:
            p[0], p[1], p[2] = r, g, b
            p[3] = self.ramp & 0xFF
        elif eid == EFFECT_BREATHE:
            p[0], p[1], p[2] = r, g, b
            per = max(100, min(65535, int(self.period)))
            p[3] = (per >> 8) & 0xFF
            p[4] = per & 0xFF
            p[5] = self.form & 0xFF
            p[6] = max(0, min(100, int(self.intensity)))
        elif eid == EFFECT_CYCLE:
            p[1] = max(0, min(255, int(self.saturation)))
            per = max(500, min(65535, int(self.period)))
            p[6] = (per >> 8) & 0xFF
            p[7] = per & 0xFF
            p[8] = max(0, min(100, int(self.intensity)))
        elif eid == EFFECT_WAVE:
            p[1] = max(0, min(255, int(self.saturation)))
            per = max(500, min(65535, int(self.period)))
            p[6] = (per >> 8) & 0xFF
            p[7] = per & 0xFF
            p[8] = max(0, min(100, int(self.intensity)))
            p[9] = max(0, min(8, int(self.direction)))
        elif eid == EFFECT_RIPPLE:
            p[0], p[1], p[2] = r, g, b
            p[3] = max(0, min(255, int(self.saturation)))
            per = max(2, min(200, int(self.period)))
            p[6] = (per >> 8) & 0xFF
            p[7] = per & 0xFF

        return bytes([eid]) + bytes(p)

    @classmethod
    def from_bytes(cls, data: bytes) -> "LedEffect":
        if len(data) != 11:
            raise ValueError(f"Expected 11 bytes for LedEffect, got {len(data)}")
        eid = data[0]
        p = data[1:]
        if eid == EFFECT_OFF:
            return cls(effect_id=EFFECT_OFF, color=0x000000, raw_bytes=data)
        if eid == EFFECT_STATIC:
            color = (p[0] << 16) | (p[1] << 8) | p[2]
            return cls(effect_id=EFFECT_STATIC, color=color, ramp=p[3], raw_bytes=data)
        if eid == EFFECT_BREATHE:
            color = (p[0] << 16) | (p[1] << 8) | p[2]
            period = (p[3] << 8) | p[4]
            return cls(
                effect_id=EFFECT_BREATHE,
                color=color,
                period=period or 5000,
                form=p[5] or 1,
                intensity=p[6] if p[6] else 100,
                raw_bytes=data,
            )
        if eid == EFFECT_CYCLE:
            sat = p[1]
            period = (p[6] << 8) | p[7]
            intensity = p[8]
            return cls(
                effect_id=EFFECT_CYCLE,
                saturation=sat or 255,
                period=period or 5000,
                intensity=intensity or 100,
                raw_bytes=data,
            )
        if eid == EFFECT_WAVE:
            sat = p[1]
            period = (p[6] << 8) | p[7]
            intensity = p[8]
            direction = p[9]
            return cls(
                effect_id=EFFECT_WAVE,
                saturation=sat or 255,
                period=period or 5000,
                intensity=intensity or 100,
                direction=direction,
                raw_bytes=data,
            )
        if eid == EFFECT_RIPPLE:
            color = (p[0] << 16) | (p[1] << 8) | p[2]
            sat = p[3]
            period = (p[6] << 8) | p[7]
            return cls(
                effect_id=EFFECT_RIPPLE,
                color=color,
                saturation=sat or 255,
                period=period or 20,
                raw_bytes=data,
            )
        return cls(effect_id=eid, raw_bytes=data)

    def to_dict(self) -> dict:
        return {
            "effect_id": self.effect_id,
            "color": format_hex_color(self.color),
            "period": self.period,
            "intensity": self.intensity,
            "saturation": self.saturation,
            "direction": self.direction,
            "ramp": self.ramp,
            "form": self.form,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LedEffect":
        return cls(
            effect_id=int(d.get("effect_id", EFFECT_STATIC)),
            color=parse_hex_color(d["color"]) if isinstance(d.get("color"), str) else int(d.get("color", 0xF552FF)),
            period=int(d.get("period", 5000)),
            intensity=int(d.get("intensity", 100)),
            saturation=int(d.get("saturation", 255)),
            direction=int(d.get("direction", 1)),
            ramp=int(d.get("ramp", 2)),
            form=int(d.get("form", 1)),
        )


@dataclasses.dataclass
class KeyBinding:
    """4-byte 0x8100 onboard button binding (F1-F12 primary or G-Shift)."""

    kind: str = "key"        # "key", "consumer", "disabled", "function", "raw"
    modifiers: int = 0       # bitmask for kind=="key"
    keycode: int = 0x3A      # USB HID keycode (kind=="key") or Consumer usage (kind=="consumer")
    func_id: int = 0         # Device function id (kind=="function")
    func_data: int = 0
    raw_bytes: bytes = b"\x80\x02\x00\x3a"

    @classmethod
    def from_bytes(cls, data: bytes) -> "KeyBinding":
        if len(data) != 4:
            raise ValueError("KeyBinding must be 4 bytes")
        behavior = data[0] >> 4
        if behavior == 0x8:
            mtype = data[1]
            if mtype == 0x00:
                return cls(kind="disabled", raw_bytes=data)
            if mtype == 0x02:
                return cls(kind="key", modifiers=data[2], keycode=data[3], raw_bytes=data)
            if mtype == 0x03:
                code = (data[2] << 8) | data[3]
                return cls(kind="consumer", keycode=code, raw_bytes=data)
        elif behavior == 0x9:
            return cls(kind="function", func_id=data[1], func_data=data[3], raw_bytes=data)
        return cls(kind="raw", raw_bytes=data)

    def to_bytes(self) -> bytes:
        if self.kind == "disabled":
            return b"\x80\x00\xff\xff"
        if self.kind == "key":
            return bytes([0x80, 0x02, self.modifiers & 0xFF, self.keycode & 0xFF])
        if self.kind == "consumer":
            return bytes([0x80, 0x03, (self.keycode >> 8) & 0xFF, self.keycode & 0xFF])
        if self.kind == "function":
            return bytes([0x90, self.func_id & 0xFF, 0xFF, self.func_data & 0xFF])
        return self.raw_bytes[:4].ljust(4, b"\xff")

    def describe(self) -> str:
        if self.kind == "disabled":
            return "Disabled"
        if self.kind == "key":
            parts = [name for bit, name in MODIFIER_BITS if self.modifiers & bit]
            parts.append(USB_HID_KEYS.get(self.keycode, f"HID 0x{self.keycode:02X}"))
            return "+".join(parts)
        if self.kind == "consumer":
            return CONSUMER_KEYS.get(self.keycode, f"Media 0x{self.keycode:04X}")
        if self.kind == "function":
            if self.func_id == 0x0B:
                return "G-Shift"
            if self.func_id == 0x0C:
                return "Battery Status"
            return f"Fn 0x{self.func_id:02X}"
        return f"Raw ({self.raw_bytes.hex()})"


@dataclasses.dataclass
class OnboardProfileData:
    """Parsed 255-byte Logitech G715 Onboard Profile (Sector 0x0001, Format 5)."""

    sector: int
    raw_sector: bytes
    report_rate_ms: int
    ps_timeout_s: int
    po_timeout_s: int
    name: str
    keys_active: LedEffect
    perimeter_active: LedEffect
    keys_dim: LedEffect
    perimeter_dim: LedEffect
    f_keys: list[KeyBinding]
    g_shift_keys: list[KeyBinding]

    @classmethod
    def from_sector_bytes(cls, data: bytes, sector: int = 1) -> "OnboardProfileData":
        if len(data) != 255:
            raise ValueError(f"Expected 255-byte G715 profile sector, got {len(data)}")
        report_rate_ms = data[0]
        ps_timeout_s = struct.unpack("<H", data[28:30])[0]
        po_timeout_s = struct.unpack("<H", data[30:32])[0]
        f_keys = [KeyBinding.from_bytes(data[32 + i * 4 : 36 + i * 4]) for i in range(12)]
        g_shift_keys = [KeyBinding.from_bytes(data[96 + i * 4 : 100 + i * 4]) for i in range(12)]
        raw_name = data[160:208]
        if raw_name == b"\xff" * 48:
            name = "Default"
        else:
            name = raw_name.decode("utf-16le", errors="replace").rstrip("\x00\uffff")
        # On Logitech 0x8100 Format 5 (G715 verified on hardware & ROM 0x0101):
        #   offset 208..218 (lighting[0]) = Perimeter Underglow (Active)
        #   offset 219..229 (lighting[1]) = Keys Backlight (Active)
        #   offset 230..240 (lighting[2]) = Perimeter Underglow (Idle / Dim)
        #   offset 241..251 (lighting[3]) = Keys Backlight (Idle / Dim)
        perimeter_active = LedEffect.from_bytes(data[208:219])
        keys_active = LedEffect.from_bytes(data[219:230])
        perimeter_dim = LedEffect.from_bytes(data[230:241])
        keys_dim = LedEffect.from_bytes(data[241:252])
        return cls(
            sector=sector,
            raw_sector=bytes(data),
            report_rate_ms=report_rate_ms,
            ps_timeout_s=ps_timeout_s,
            po_timeout_s=po_timeout_s,
            name=name,
            keys_active=keys_active,
            perimeter_active=perimeter_active,
            keys_dim=keys_dim,
            perimeter_dim=perimeter_dim,
            f_keys=f_keys,
            g_shift_keys=g_shift_keys,
        )

    def to_sector_bytes(self) -> bytes:
        """Patch all edited fields into a copy of raw_sector and recompute CRC16-CCITT."""
        buf = bytearray(self.raw_sector if len(self.raw_sector) == 255 else b"\xff" * 255)
        buf[0] = self.report_rate_ms & 0xFF
        buf[28:30] = struct.pack("<H", max(0, min(65535, int(self.ps_timeout_s))))
        buf[30:32] = struct.pack("<H", max(0, min(65535, int(self.po_timeout_s))))

        for i in range(12):
            buf[32 + i * 4 : 36 + i * 4] = self.f_keys[i].to_bytes()
        for i in range(12):
            buf[96 + i * 4 : 100 + i * 4] = self.g_shift_keys[i].to_bytes()

        encoded_name = self.name[:24].ljust(24, "\x00").encode("utf-16le")
        buf[160:208] = encoded_name

        buf[208:219] = self.perimeter_active.to_bytes()
        buf[219:230] = self.keys_active.to_bytes()
        buf[230:241] = self.perimeter_dim.to_bytes()
        buf[241:252] = self.keys_dim.to_bytes()

        # Byte 252 is preserved from original sector (0x00 on G HUB, 0x03 on ROM)
        crc = crc16_ccitt(bytes(buf[:253]))
        buf[253] = (crc >> 8) & 0xFF
        buf[254] = crc & 0xFF
        return bytes(buf)


@dataclasses.dataclass
class BootAnimation:
    kind: str         # "startup" or "shutdown"
    enabled: bool
    color1: int       # 0xRRGGBB
    color2: int       # 0xRRGGBB


@dataclasses.dataclass
class BatteryStatus:
    percentage: int
    charging: bool
    status_code: int

    @property
    def status_text(self) -> str:
        return {
            0: "Discharging",
            1: "Charging",
            2: "Almost Full",
            3: "Fully Charged",
            4: "Slow Charging",
            5: "Invalid Battery",
            6: "Thermal Error",
        }.get(self.status_code, f"Status {self.status_code}")


@dataclasses.dataclass
class DeviceStatus:
    name: str
    connection: str
    hidraw_path: str
    protocol_version: str
    battery: Optional[BatteryStatus]
    onboard_mode: bool
    sw_control: bool
    active_profile_sector: int
    brightness_pct: int
    report_rate_ms: int
    sector_count: int
    sector_size: int


class G715Device:
    """High-level controller for the Logitech G715 keyboard."""

    def __init__(self, transport: HidppTransport, candidate: Optional[DeviceCandidate] = None):
        self.transport = transport
        self.candidate = candidate
        self._zone_effect_indices: Optional[dict[int, dict[int, int]]] = None
        self._present_zones: Optional[list[int]] = None

    @classmethod
    def connect(cls, candidate: Optional[DeviceCandidate] = None) -> "G715Device":
        if candidate is None:
            devices = discover_g715_devices()
            if not devices:
                raise HidppError(
                    "No Logitech G715 found over USB, Lightspeed receiver, or Bluetooth. "
                    "Make sure it is turned on and check udev permissions."
                )
            # Prefer wired USB if both wired and wireless are somehow present
            devices.sort(key=lambda d: {"usb": 0, "lightspeed": 1, "bluetooth": 2}.get(d.connection, 3))
            candidate = devices[0]
        tr = HidppTransport(
            candidate.hidraw_path,
            dev_idx=candidate.dev_idx,
            connection=candidate.connection,
            pid=candidate.pid,
        )
        tr.open()
        tr.ping()
        return cls(tr, candidate)

    def close(self) -> None:
        self.transport.close()

    def __enter__(self) -> "G715Device":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    # --- Status & Info ---

    def get_battery(self) -> Optional[BatteryStatus]:
        try:
            r = self.transport.feature_request(FEAT_UNIFIED_BATTERY, 0x01)
            pct = r[0]
            status_code = r[2]
            charging = status_code in (1, 2, 3, 4)
            return BatteryStatus(percentage=pct, charging=charging, status_code=status_code)
        except HidppError:
            return None

    def get_brightness(self) -> int:
        r = self.transport.feature_request(FEAT_BRIGHTNESS, 0x01)
        return (r[0] << 8) | r[1]

    def set_brightness(self, pct: int) -> None:
        val = max(0, min(100, int(pct)))
        self.transport.feature_request(FEAT_BRIGHTNESS, 0x02, bytes([(val >> 8) & 0xFF, val & 0xFF]))

    def get_report_rate(self) -> int:
        r = self.transport.feature_request(FEAT_REPORT_RATE, 0x01)
        return r[0]

    def set_report_rate(self, rate_ms: int) -> None:
        if rate_ms not in (1, 2, 4, 8):
            raise ValueError("Report rate must be 1 (1000Hz), 2 (500Hz), 4 (250Hz), or 8 (125Hz) ms")
        self.transport.feature_request(FEAT_REPORT_RATE, 0x02, bytes([rate_ms]))

    def get_onboard_desc(self) -> tuple[int, int]:
        """Return (sector_count, sector_size)."""
        r = self.transport.feature_request(FEAT_ONBOARD_PROFILES, 0x00)
        sec_count = r[6]
        sec_size = (r[7] << 8) | r[8]
        return sec_count, sec_size

    def get_onboard_mode(self) -> bool:
        """Return True if keyboard is in Onboard Memory Mode (0x01), False if Host Mode (0x02)."""
        r = self.transport.feature_request(FEAT_ONBOARD_PROFILES, 0x02)
        return r[0] == 0x01

    def set_onboard_mode(self, onboard: bool) -> None:
        mode = 0x01 if onboard else 0x02
        self.transport.feature_request(FEAT_ONBOARD_PROFILES, 0x01, bytes([mode]))

    def get_active_profile_sector(self) -> int:
        r = self.transport.feature_request(FEAT_ONBOARD_PROFILES, 0x04)
        return (r[0] << 8) | r[1]

    def set_active_profile_sector(self, sector: int) -> None:
        self.transport.feature_request(FEAT_ONBOARD_PROFILES, 0x03, bytes([(sector >> 8) & 0xFF, sector & 0xFF]))

    def get_sw_control(self) -> bool:
        r = self.transport.feature_request(FEAT_RGB_EFFECTS, 0x05, b"\x00")
        return len(r) >= 2 and r[1] != 0

    def get_status(self) -> DeviceStatus:
        name = self.candidate.device_name if self.candidate else self.transport.get_device_name()
        ver = f"{self.transport.protocol_version[0]}.{self.transport.protocol_version[1]}"
        sec_cnt, sec_sz = self.get_onboard_desc()
        return DeviceStatus(
            name=name,
            connection=self.transport.connection,
            hidraw_path=self.transport.hidraw_path,
            protocol_version=ver,
            battery=self.get_battery(),
            onboard_mode=self.get_onboard_mode(),
            sw_control=self.get_sw_control(),
            active_profile_sector=self.get_active_profile_sector(),
            brightness_pct=self.get_brightness(),
            report_rate_ms=self.get_report_rate(),
            sector_count=sec_cnt,
            sector_size=sec_sz,
        )

    # --- 0x8100 Onboard Memory Flash I/O ---

    def read_sector(self, sector: int, size: int = 255) -> bytes:
        buf = bytearray()
        off = 0
        while off < size - 15:
            chunk = self.transport.feature_request(
                FEAT_ONBOARD_PROFILES,
                0x05,
                bytes([(sector >> 8) & 0xFF, sector & 0xFF, (off >> 8) & 0xFF, off & 0xFF]),
            )
            buf.extend(chunk[:16])
            off += 16
        tail_off = size - 16
        chunk = self.transport.feature_request(
            FEAT_ONBOARD_PROFILES,
            0x05,
            bytes([(sector >> 8) & 0xFF, sector & 0xFF, (tail_off >> 8) & 0xFF, tail_off & 0xFF]),
        )
        buf.extend(chunk[16 + off - size : 16])
        return bytes(buf[:size])

    def write_sector(self, sector: int, data: bytes, verify: bool = True) -> bool:
        """Write a 255-byte sector to 0x8100 flash memory with CRC check and read-back verification."""
        sec_cnt, sec_sz = self.get_onboard_desc()
        if sector >= sec_cnt:
            raise HidppError(f"Sector 0x{sector:04X} is out of writable range (0..{sec_cnt - 1})")
        if len(data) != sec_sz:
            raise ValueError(f"Sector data must be exactly {sec_sz} bytes, got {len(data)}")

        # Verify CRC16-CCITT before touching flash!
        expected_crc = crc16_ccitt(data[:-2])
        actual_crc = (data[-2] << 8) | data[-1]
        if expected_crc != actual_crc:
            raise ValueError(f"Refusing to write sector with invalid CRC (expected 0x{expected_crc:04X}, got 0x{actual_crc:04X})")

        existing = self.read_sector(sector, sec_sz)
        if existing == data:
            return False

        # Begin write (func 6)
        self.transport.feature_request(
            FEAT_ONBOARD_PROFILES,
            0x06,
            bytes([
                (sector >> 8) & 0xFF, sector & 0xFF,
                0x00, 0x00,
                (len(data) >> 8) & 0xFF, len(data) & 0xFF,
            ]),
        )
        # Stream 16-byte chunks (func 7)
        for off in range(0, len(data), 16):
            chunk = data[off : off + 16]
            self.transport.feature_request(FEAT_ONBOARD_PROFILES, 0x07, chunk)
        # Commit flash write (func 8)
        self.transport.feature_request(FEAT_ONBOARD_PROFILES, 0x08)

        if verify:
            time.sleep(0.05)
            readback = self.read_sector(sector, sec_sz)
            if readback != data:
                raise HidppError(f"Flash verification failed on sector 0x{sector:04X}!")
        return True

    def read_onboard_profile(self, sector: int = 1) -> OnboardProfileData:
        _, sec_sz = self.get_onboard_desc()
        raw = self.read_sector(sector, sec_sz)
        return OnboardProfileData.from_sector_bytes(raw, sector=sector)

    def write_onboard_profile(self, profile: OnboardProfileData, activate: bool = True) -> bool:
        """Persist profile to onboard flash, release SW control, and activate immediately."""
        sector_bytes = profile.to_sector_bytes()
        written = self.write_sector(profile.sector, sector_bytes, verify=True)

        # Ensure sector 0 directory points to sector 1 as enabled
        dir_raw = self.read_sector(0, len(sector_bytes))
        if dir_raw[0:3] != bytes([(profile.sector >> 8) & 0xFF, profile.sector & 0xFF, 0x01]):
            dir_buf = bytearray(b"\xff" * len(sector_bytes))
            dir_buf[0] = (profile.sector >> 8) & 0xFF
            dir_buf[1] = profile.sector & 0xFF
            dir_buf[2] = 0x01
            crc = crc16_ccitt(bytes(dir_buf[:-2]))
            dir_buf[-2] = (crc >> 8) & 0xFF
            dir_buf[-1] = crc & 0xFF
            self.write_sector(0, bytes(dir_buf), verify=True)

        if activate:
            # Release SW lighting override so hardware immediately renders onboard flash
            try:
                self.transport.feature_request(FEAT_RGB_EFFECTS, 0x05, SW_RELEASE)
            except HidppError:
                pass
            self.set_onboard_mode(True)
            # Re-selecting active profile reloads lighting from flash immediately
            self.set_active_profile_sector(profile.sector)
        return written

    def restore_factory_profile_from_rom(self) -> OnboardProfileData:
        """Read factory ROM sector 0x0101, fix CRC, write to Sector 0x0001, and activate."""
        _, sec_sz = self.get_onboard_desc()
        rom = bytearray(self.read_sector(0x0101, sec_sz))
        crc = crc16_ccitt(bytes(rom[:-2]))
        rom[-2] = (crc >> 8) & 0xFF
        rom[-1] = crc & 0xFF
        profile = OnboardProfileData.from_sector_bytes(bytes(rom), sector=1)
        self.write_onboard_profile(profile, activate=True)
        return profile

    def dump_all_sectors(self) -> dict[str, str]:
        sec_cnt, sec_sz = self.get_onboard_desc()
        out: dict[str, str] = {}
        for sec in list(range(sec_cnt)) + [0x0100, 0x0101]:
            try:
                out[f"0x{sec:04x}"] = self.read_sector(sec, sec_sz).hex()
            except HidppError:
                pass
        return out

    def restore_sectors(self, sectors: dict[str, str]) -> int:
        sec_cnt, _ = self.get_onboard_desc()
        count = 0
        for key, hexdata in sectors.items():
            sec = int(key, 16)
            if sec < sec_cnt and hexdata:
                raw = bytes.fromhex(hexdata)
                # Only write sectors that have a valid CRC (skip erased 0xFF sectors)
                if len(raw) == 255 and crc16_ccitt(raw[:-2]) == ((raw[-2] << 8) | raw[-1]):
                    if self.write_sector(sec, raw, verify=True):
                        count += 1
        try:
            self.transport.feature_request(FEAT_RGB_EFFECTS, 0x05, SW_RELEASE)
        except HidppError:
            pass
        self.set_onboard_mode(True)
        self.set_active_profile_sector(1)
        return count

    # --- 0x8071 NvConfig Persistent Startup & Shutdown Animations ---

    def get_boot_animation(self, kind: str) -> BootAnimation:
        cap = 0x0001 if kind == "startup" else 0x0040
        r = self.transport.feature_request(FEAT_RGB_EFFECTS, 0x03, bytes([0x00, (cap >> 8) & 0xFF, cap & 0xFF]))
        # Reply: [subfn, capHi, capLo, enabled(1=on,2=off), R1, G1, B1, R2, G2, B2]
        enabled = r[3] == 0x01
        c1 = (r[4] << 16) | (r[5] << 8) | r[6]
        c2 = (r[7] << 16) | (r[8] << 8) | r[9]
        return BootAnimation(kind=kind, enabled=enabled, color1=c1, color2=c2)

    def set_boot_animation(self, anim: BootAnimation) -> None:
        cap = 0x0001 if anim.kind == "startup" else 0x0040
        payload = bytes([
            0x01,
            (cap >> 8) & 0xFF,
            cap & 0xFF,
            0x01 if anim.enabled else 0x02,
            (anim.color1 >> 16) & 0xFF,
            (anim.color1 >> 8) & 0xFF,
            anim.color1 & 0xFF,
            (anim.color2 >> 16) & 0xFF,
            (anim.color2 >> 8) & 0xFF,
            anim.color2 & 0xFF,
        ])
        self.transport.feature_request(FEAT_RGB_EFFECTS, 0x03, payload)

    # --- 0x8071 Software Control & Live Zone Effects ---

    def claim_sw_control(self) -> None:
        """Take live software lighting ownership (required for live previews & 0x8081 per-key painting)."""
        self.set_onboard_mode(False)
        self.transport.feature_request(FEAT_RGB_EFFECTS, 0x05, SW_ACTIVE)

    def release_sw_control(self) -> None:
        """Release software lighting ownership back to onboard flash profile."""
        self.transport.feature_request(FEAT_RGB_EFFECTS, 0x05, SW_RELEASE)
        self.set_onboard_mode(True)
        self.set_active_profile_sector(1)

    def _load_zone_effect_table(self) -> dict[int, dict[int, int]]:
        if self._zone_effect_indices is not None:
            return self._zone_effect_indices
        info = self.transport.feature_request(FEAT_RGB_EFFECTS, 0x00, bytes([0xFF, 0xFF, 0x00]))
        _, _, zone_count, _, _ = struct.unpack("!BBBHH", info[0:7])
        table: dict[int, dict[int, int]] = {}
        for z in range(zone_count):
            zi = self.transport.feature_request(FEAT_RGB_EFFECTS, 0x00, bytes([z, 0xFF, 0x00]))
            _, eff_count = struct.unpack("!HB", zi[2:5])
            table[z] = {}
            for e in range(eff_count):
                ei = self.transport.feature_request(FEAT_RGB_EFFECTS, 0x00, bytes([z, e, 0x00]))
                _, eidx, eid, _, _ = struct.unpack("!BBHHH", ei[0:8])
                table[z][eid] = eidx
        self._zone_effect_indices = table
        return table

    def set_live_zone_effect(self, zone_idx: int, effect: LedEffect) -> None:
        """Apply a live volatile effect to Zone 0 (Keys) or Zone 1 (Perimeter) via 0x8071."""
        table = self._load_zone_effect_table()
        if zone_idx not in table:
            raise HidppError(f"Zone {zone_idx} not available on this device")
        eff_map = table[zone_idx]
        if effect.effect_id not in eff_map:
            raise HidppError(f"Effect 0x{effect.effect_id:02X} not supported on live zone {zone_idx}")
        eidx = eff_map[effect.effect_id]
        raw = effect.to_bytes()
        # 0x8071 func 1: [0x01, zone_idx, effect_slot_index, ...10 param bytes]
        payload = bytes([0x01, zone_idx, eidx]) + raw[1:]
        self.transport.feature_request(FEAT_RGB_EFFECTS, 0x01, payload)

    # --- 0x8081 Per-Key & 16-LED Perimeter RGB Control ---

    def get_present_led_zones(self) -> list[int]:
        """Query 0x8081 getRgbZonePresence across all 3 pages and return valid zone IDs."""
        if self._present_zones is not None:
            return list(self._present_zones)
        bitmap = bytearray()
        for page in range(3):
            r = self.transport.feature_request(FEAT_PER_KEY_V2, 0x00, bytes([0x00, page]))
            bitmap.extend(r[2:16])
        zones = [i for i in range(1, min(255, len(bitmap) * 8)) if (bitmap[i // 8] >> (i % 8)) & 1]
        self._present_zones = zones
        return list(zones)

    def apply_perkey_frame(
        self,
        zone_colors: dict[int, int],
        base_color: Optional[int] = None,
        ensure_sw_control: bool = True,
        persist_flag: int = 0x00,
    ) -> None:
        """Push a complete per-key + 16-LED perimeter RGB frame over 0x8081 and commit with FrameEnd.

        If base_color is provided, all present zones not in zone_colors are filled with base_color.
        """
        if ensure_sw_control and not self.get_sw_control():
            self.claim_sw_control()
            # Ensure both zones are in Static mode so 0x8081 per-key buffer owns the visible layer
            self.set_live_zone_effect(0, LedEffect(effect_id=EFFECT_STATIC, color=base_color or 0x000000))
            self.set_live_zone_effect(1, LedEffect(effect_id=EFFECT_STATIC, color=base_color or 0x000000))

        present = set(self.get_present_led_zones())
        merged: dict[int, int] = {}
        if base_color is not None:
            for z in present:
                merged[z] = base_color & 0xFFFFFF
        for z, col in zone_colors.items():
            if z in present:
                merged[z] = col & 0xFFFFFF

        if not merged:
            return

        # Bucket zones by RGB color for fast batching (func 0x06 packs 13 zones per packet!)
        buckets: dict[int, list[int]] = {}
        for z, col in sorted(merged.items()):
            buckets.setdefault(col, []).append(z)

        indiv_buf = bytearray()
        for col, zones in buckets.items():
            rgb = bytes([(col >> 16) & 0xFF, (col >> 8) & 0xFF, col & 0xFF])
            while len(zones) > 3:
                batch = zones[:13]
                zones = zones[13:]
                self.transport.feature_request(FEAT_PER_KEY_V2, 0x06, rgb + bytes(batch))
            for z in zones:
                indiv_buf.append(z)
                indiv_buf.extend(rgb)
                if len(indiv_buf) >= 16:
                    self.transport.feature_request(FEAT_PER_KEY_V2, 0x01, bytes(indiv_buf[:16]))
                    del indiv_buf[:16]

        if indiv_buf:
            self.transport.feature_request(FEAT_PER_KEY_V2, 0x01, bytes(indiv_buf))

        # Commit frame (func 0x07: FrameEnd)
        self.transport.feature_request(FEAT_PER_KEY_V2, 0x07, bytes([persist_flag & 0xFF]))
