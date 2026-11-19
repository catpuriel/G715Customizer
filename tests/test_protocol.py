"""Unit tests for Logitech G715 HID++ protocol serialization & CRC16 integrity."""

import unittest

from g715.layout import G715_LAYOUT, PERIMETER_ZONE_IDS
from g715.protocol import (
    EFFECT_BREATHE,
    EFFECT_CYCLE,
    EFFECT_OFF,
    EFFECT_RIPPLE,
    EFFECT_STATIC,
    EFFECT_WAVE,
    KeyBinding,
    LedEffect,
    OnboardProfileData,
    crc16_ccitt,
    dim_color,
    format_hex_color,
    parse_hex_color,
)

# Real Sector 0x0001 captured from a Logitech G715 (255 bytes, CRC = 0xEF4D)
REAL_G715_SECTOR_1_HEX = (
    "010100900120034006800c0000ffffff"
    "ff00ffffffffffffffffffffffff2c01"
    "8002003a8002003b8002003c8002003d"
    "8002003e8002003f8002004080020041"
    "80020042800200438002004480020045"
    "ffffffffffffffffffffffffffffffff"
    "8002003a8002003b8002003c8002003d"
    "8002003e8002003f8002004080020041"
    "80020042800200438002004480020045"
    "ffffffffffffffffffffffffffffffff"
    "500052004f00460049004c0045005f00"
    "4e0041004d0045005f00440045004600"
    "410055004c0054000000000000000000"
    "01f552ff0200000000000001f552ff02"
    "000000000000017a297f020000000000"
    "00017a297f0200000000000000ef4d"
)


class TestProtocol(unittest.TestCase):
    def test_crc16_matches_real_g715_sector(self) -> None:
        raw = bytes.fromhex(REAL_G715_SECTOR_1_HEX)
        self.assertEqual(len(raw), 255)
        expected = (raw[-2] << 8) | raw[-1]
        self.assertEqual(expected, 0xEF4D)
        self.assertEqual(crc16_ccitt(raw[:-2]), expected)

    def test_profile_roundtrip_bit_identical(self) -> None:
        raw = bytes.fromhex(REAL_G715_SECTOR_1_HEX)
        prof = OnboardProfileData.from_sector_bytes(raw, sector=1)
        self.assertEqual(prof.name, "PROFILE_NAME_DEFAULT")
        self.assertEqual(prof.report_rate_ms, 1)
        self.assertEqual(prof.ps_timeout_s, 0xFFFF)
        self.assertEqual(prof.po_timeout_s, 300)
        self.assertEqual(prof.keys_active.effect_id, EFFECT_STATIC)
        self.assertEqual(prof.keys_active.color, 0xF552FF)
        self.assertEqual(prof.perimeter_active.color, 0xF552FF)
        self.assertEqual(prof.keys_dim.color, 0x7A297F)
        self.assertEqual(prof.perimeter_dim.color, 0x7A297F)
        self.assertEqual(len(prof.f_keys), 12)
        self.assertEqual(prof.f_keys[0].describe(), "F1")
        self.assertEqual(prof.f_keys[11].describe(), "F12")

        # Re-serializing without changes must be 100% bit-for-bit identical!
        rebuilt = prof.to_sector_bytes()
        self.assertEqual(rebuilt, raw)

    def test_profile_edit_updates_crc_and_preserves_byte_252(self) -> None:
        raw = bytes.fromhex(REAL_G715_SECTOR_1_HEX)
        prof = OnboardProfileData.from_sector_bytes(raw, sector=1)
        prof.keys_active = LedEffect(EFFECT_STATIC, color=0xFF73B9)
        prof.perimeter_active = LedEffect(EFFECT_STATIC, color=0x6BE5F5)
        rebuilt = prof.to_sector_bytes()
        self.assertEqual(len(rebuilt), 255)
        self.assertEqual(rebuilt[252], 0x00)
        self.assertEqual(crc16_ccitt(rebuilt[:-2]), (rebuilt[-2] << 8) | rebuilt[-1])

        reparsed = OnboardProfileData.from_sector_bytes(rebuilt, sector=1)
        self.assertEqual(reparsed.keys_active.color, 0xFF73B9)
        self.assertEqual(reparsed.perimeter_active.color, 0x6BE5F5)
        # Verify exact hardware sector offsets: perimeter=208..218, keys=219..229
        self.assertEqual(rebuilt[209:212], bytes([0x6B, 0xE5, 0xF5]))
        self.assertEqual(rebuilt[220:223], bytes([0xFF, 0x73, 0xB9]))

    def test_led_effect_roundtrip_all_modes(self) -> None:
        cases = [
            LedEffect(EFFECT_OFF),
            LedEffect(EFFECT_STATIC, color=0x123456, ramp=2),
            LedEffect(EFFECT_BREATHE, color=0xAA55FF, period=4200, form=1, intensity=80),
            LedEffect(EFFECT_CYCLE, saturation=200, period=6000, intensity=90),
            LedEffect(EFFECT_WAVE, saturation=255, period=3500, intensity=100, direction=6),
            LedEffect(EFFECT_RIPPLE, color=0x00FFAA, saturation=240, period=25),
        ]
        for eff in cases:
            b = eff.to_bytes()
            self.assertEqual(len(b), 11)
            back = LedEffect.from_bytes(b)
            self.assertEqual(back.to_bytes(), b)

    def test_key_binding_roundtrip(self) -> None:
        cases = [
            KeyBinding(kind="key", modifiers=0x03, keycode=0x06),       # LCtrl+LShift+C
            KeyBinding(kind="consumer", keycode=0x00CD),                # Play/Pause
            KeyBinding(kind="disabled"),
            KeyBinding(kind="function", func_id=0x0B, func_data=0x00),  # G-Shift
        ]
        for kb in cases:
            b = kb.to_bytes()
            self.assertEqual(len(b), 4)
            self.assertEqual(KeyBinding.from_bytes(b).to_bytes(), b)

    def test_color_helpers_and_layout(self) -> None:
        self.assertEqual(parse_hex_color("#ff73b9"), 0xFF73B9)
        self.assertEqual(format_hex_color(0x00ABCD), "#00ABCD")
        self.assertEqual(dim_color(0xF452FE, 0.5), 0x7A297F)
        self.assertEqual(len(PERIMETER_ZONE_IDS), 16)
        # Ensure all layout zone IDs are unique
        zids = [c.zone_id for c in G715_LAYOUT]
        self.assertEqual(len(zids), len(set(zids)))


if __name__ == "__main__":
    unittest.main()
