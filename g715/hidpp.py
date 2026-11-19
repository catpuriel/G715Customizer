"""Pure-Python Logitech HID++ 2.0/4.2 transport over Linux /dev/hidraw*.

Supports:
  - Wired USB G715 (046d:c347, dev_idx=0xFF)
  - Lightspeed wireless receivers (046d:c547, c54d, c539, c53f, c541, c545, c548; dev_idx=1..6)
  - Bluetooth G715 (046d:b368, dev_idx=0xFF)
"""

from __future__ import annotations

import dataclasses
import glob
import os
import select
import threading
import time
from typing import Optional

LOGITECH_VID = 0x046D
G715_USB_PID = 0xC347
G715_BT_PID = 0xB368
G715_WPID = 0x40A2

LIGHTSPEED_RECEIVER_PIDS = frozenset({
    0xC539,  # Lightspeed Receiver
    0xC53F,  # Lightspeed Receiver
    0xC541,  # Lightspeed Receiver
    0xC545,  # Lightspeed Receiver
    0xC547,  # Lightspeed Receiver (G715 / G502 X / Aurora)
    0xC548,  # Logi Bolt (just in case)
    0xC54D,  # Lightspeed Receiver (newer)
})

REPORT_ID_SHORT = 0x10
REPORT_ID_LONG = 0x11

HIDPP_ERRORS = {
    0x00: "NO_ERROR",
    0x01: "UNKNOWN",
    0x02: "INVALID_ARGUMENT",
    0x03: "OUT_OF_RANGE",
    0x04: "HW_ERROR",
    0x05: "LOGITECH_INTERNAL",
    0x06: "INVALID_FEATURE_INDEX",
    0x07: "INVALID_FUNCTION_ID",
    0x08: "BUSY",
    0x09: "UNSUPPORTED",
}


class HidppError(Exception):
    """Raised when a HID++ command fails or returns an error packet."""

    def __init__(self, message: str, error_code: Optional[int] = None):
        super().__init__(message)
        self.error_code = error_code


@dataclasses.dataclass
class DeviceCandidate:
    hidraw_path: str
    vid: int
    pid: int
    hid_name: str
    connection: str  # "usb", "lightspeed", "bluetooth"
    dev_idx: int
    device_name: str = ""
    protocol_version: str = ""


def _parse_uevent(path: str) -> dict[str, str]:
    info: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    info[k] = v
    except OSError:
        pass
    return info


def _has_hidpp_usage_page(hidraw_name: str) -> bool:
    """Check if the HID report descriptor exposes Logitech HID++ Usage Page 0xFF00 or 0xFF43."""
    desc_path = f"/sys/class/hidraw/{hidraw_name}/device/report_descriptor"
    try:
        with open(desc_path, "rb") as f:
            data = f.read()
    except OSError:
        return False
    # Usage Page (Vendor Defined 0xFF00): 06 00 ff  |  Bluetooth HID++ (0xFF43): 06 43 ff
    # Also ensure Report ID 0x11 (85 11) is present for HID++ Long reports.
    has_vendor = (b"\x06\x00\xff" in data) or (b"\x06\x43\xff" in data)
    has_long_report = b"\x85\x11" in data
    return has_vendor and has_long_report


class HidppTransport:
    """Thread-safe HID++ 2.0/4.2 transport bound to a single /dev/hidrawN endpoint."""

    def __init__(self, hidraw_path: str, dev_idx: int = 0xFF, connection: str = "usb", pid: int = G715_USB_PID):
        self.hidraw_path = hidraw_path
        self.dev_idx = dev_idx
        self.connection = connection
        self.pid = pid
        self._fd: Optional[int] = None
        self._lock = threading.RLock()
        self._sw_id = 0x0A
        self._feature_cache: dict[int, tuple[int, int, int]] = {}  # feature_id -> (idx, type, version)
        self.protocol_version: tuple[int, int] = (0, 0)

    def open(self) -> None:
        with self._lock:
            if self._fd is not None:
                return
            try:
                self._fd = os.open(self.hidraw_path, os.O_RDWR | os.O_NONBLOCK)
            except PermissionError as e:
                raise HidppError(
                    f"Permission denied opening {self.hidraw_path}. "
                    "Install udev/99-logitech-g715.rules and replug the keyboard (or run udevadm trigger)."
                ) from e
            except OSError as e:
                raise HidppError(f"Failed to open {self.hidraw_path}: {e}") from e

    def close(self) -> None:
        with self._lock:
            if self._fd is not None:
                try:
                    os.close(self._fd)
                except OSError:
                    pass
                self._fd = None

    @property
    def is_open(self) -> bool:
        return self._fd is not None

    def __enter__(self) -> "HidppTransport":
        self.open()
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def _drain(self) -> None:
        """Clear any stale notifications waiting in the kernel hidraw buffer."""
        if self._fd is None:
            return
        while True:
            r, _, _ = select.select([self._fd], [], [], 0.0)
            if not r:
                break
            try:
                os.read(self._fd, 64)
            except BlockingIOError:
                break
            except OSError:
                break

    def raw_request(
        self,
        feature_idx: int,
        function_id: int,
        params: bytes = b"",
        timeout: float = 1.5,
        retries: int = 3,
    ) -> bytes:
        """Send a HID++ Long (0x11) request and return the 16-byte response payload."""
        with self._lock:
            if self._fd is None:
                self.open()
            assert self._fd is not None

            busy_delays = (0.03, 0.06, 0.12, 0.25)
            last_err: Optional[Exception] = None

            for attempt in range(retries + 1):
                self._sw_id = ((self._sw_id + 1) & 0x0F) or 0x02
                sw_id = self._sw_id
                padded = params.ljust(16, b"\x00")[:16]
                packet = bytes([
                    REPORT_ID_LONG,
                    self.dev_idx,
                    feature_idx & 0xFF,
                    ((function_id & 0x0F) << 4) | sw_id,
                ]) + padded

                self._drain()
                try:
                    os.write(self._fd, packet)
                except OSError as e:
                    raise HidppError(f"HID write failed on {self.hidraw_path}: {e}") from e

                deadline = time.monotonic() + timeout
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        last_err = HidppError(
                            f"HID++ timeout waiting for feat=0x{feature_idx:02X} func=0x{function_id:X}"
                        )
                        break

                    r, _, _ = select.select([self._fd], [], [], min(remaining, 0.2))
                    if not r:
                        continue
                    try:
                        resp = os.read(self._fd, 64)
                    except BlockingIOError:
                        continue
                    except OSError as e:
                        raise HidppError(f"HID read failed on {self.hidraw_path}: {e}") from e

                    if len(resp) < 7 or resp[0] not in (REPORT_ID_SHORT, REPORT_ID_LONG):
                        continue
                    if resp[1] != self.dev_idx:
                        continue

                    # HID++ 2.0 Error packet: [report_id, dev_idx, 0xFF, feat_idx, func_sw, err_code, ...]
                    if resp[2] == 0xFF and resp[3] == (feature_idx & 0xFF) and (resp[4] & 0x0F) == sw_id:
                        err_code = resp[5]
                        err_name = HIDPP_ERRORS.get(err_code, f"0x{err_code:02X}")
                        if err_code == 0x08 and attempt < retries:  # BUSY
                            time.sleep(busy_delays[min(attempt, len(busy_delays) - 1)])
                            last_err = HidppError(f"Device BUSY on feat=0x{feature_idx:02X}", err_code)
                            break
                        raise HidppError(
                            f"HID++ error {err_name} (0x{err_code:02X}) on feat=0x{feature_idx:02X} func=0x{function_id:X}",
                            error_code=err_code,
                        )

                    # HID++ 1.0 Error packet (e.g., offline wireless device): [0x10, dev_idx, 0x8F, ...]
                    if resp[2] == 0x8F:
                        err_code = resp[5]
                        raise HidppError(f"HID++ 1.0 error 0x{err_code:02X} (device may be asleep/offline)", err_code)

                    # Normal matching reply
                    if resp[2] == (feature_idx & 0xFF) and ((resp[3] >> 4) == (function_id & 0x0F)) and (resp[3] & 0x0F) == sw_id:
                        return resp[4:]

            raise last_err or HidppError("HID++ request failed")

    def ping(self, timeout: float = 0.6) -> tuple[int, int]:
        """Ping root feature (0x0000, func 1). Returns (major, minor) HID++ version."""
        reply = self.raw_request(0x00, 0x01, b"\x00\x00\xAA", timeout=timeout, retries=1)
        if len(reply) < 3 or reply[2] != 0xAA:
            raise HidppError("Invalid ping reply")
        self.protocol_version = (reply[0], reply[1])
        return self.protocol_version

    def get_feature_index(self, feature_id: int) -> int:
        """Resolve a 16-bit HID++ feature ID to its runtime 8-bit index."""
        if feature_id == 0x0000:
            return 0
        if feature_id in self._feature_cache:
            return self._feature_cache[feature_id][0]
        reply = self.raw_request(0x00, 0x00, bytes([(feature_id >> 8) & 0xFF, feature_id & 0xFF]))
        idx, ftype, fver = reply[0], reply[1], reply[2]
        if idx == 0:
            raise HidppError(f"Feature 0x{feature_id:04X} not supported by device")
        self._feature_cache[feature_id] = (idx, ftype, fver)
        return idx

    def has_feature(self, feature_id: int) -> bool:
        try:
            self.get_feature_index(feature_id)
            return True
        except HidppError:
            return False

    def feature_request(
        self,
        feature_id: int,
        function_id: int,
        params: bytes = b"",
        timeout: float = 1.5,
        retries: int = 3,
    ) -> bytes:
        idx = self.get_feature_index(feature_id)
        return self.raw_request(idx, function_id, params, timeout=timeout, retries=retries)

    def get_device_name(self) -> str:
        """Read the device's human-readable name via feature 0x0005 (DeviceNameAndType)."""
        r0 = self.feature_request(0x0005, 0x00)
        length = r0[0]
        chunks = bytearray()
        while len(chunks) < length:
            chunk = self.feature_request(0x0005, 0x01, bytes([len(chunks)]))
            chunks.extend(chunk)
        return bytes(chunks[:length]).decode("utf-8", errors="replace").strip()

    def get_model_id_hex(self) -> str:
        """Read model ID via 0x0003 (DeviceFwVersion func 0)."""
        r = self.feature_request(0x0003, 0x00)
        # Bytes 7..12 contain the 6-byte modelId (e.g. C347B36840A2 or similar)
        if len(r) >= 13:
            return r[7:13].hex().upper()
        return ""


def discover_g715_devices() -> list[DeviceCandidate]:
    """Scan all /dev/hidraw* endpoints for wired USB, Lightspeed wireless, or Bluetooth G715 keyboards."""
    found: list[DeviceCandidate] = []

    for sys_path in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        hidraw_name = os.path.basename(sys_path)
        dev_path = f"/dev/{hidraw_name}"
        uevent = _parse_uevent(os.path.join(sys_path, "device", "uevent"))
        hid_id = uevent.get("HID_ID", "")
        hid_name = uevent.get("HID_NAME", "")

        parts = hid_id.split(":")
        if len(parts) != 3:
            continue
        try:
            vid = int(parts[1], 16)
            pid = int(parts[2], 16)
        except ValueError:
            continue

        if vid != LOGITECH_VID:
            continue
        if not _has_hidpp_usage_page(hidraw_name):
            continue

        # 1. Direct wired USB G715
        if pid == G715_USB_PID:
            cand = _probe_endpoint(dev_path, vid, pid, hid_name, "usb", 0xFF)
            if cand:
                found.append(cand)
        # 2. Direct Bluetooth G715
        elif pid == G715_BT_PID:
            cand = _probe_endpoint(dev_path, vid, pid, hid_name, "bluetooth", 0xFF)
            if cand:
                found.append(cand)
        # 3. Lightspeed wireless receiver — probe paired device slots 1..6
        elif pid in LIGHTSPEED_RECEIVER_PIDS:
            for slot in range(1, 7):
                cand = _probe_endpoint(dev_path, vid, pid, hid_name, "lightspeed", slot, require_g715=True)
                if cand:
                    found.append(cand)

    return found


def _probe_endpoint(
    dev_path: str,
    vid: int,
    pid: int,
    hid_name: str,
    connection: str,
    dev_idx: int,
    require_g715: bool = False,
) -> Optional[DeviceCandidate]:
    try:
        with HidppTransport(dev_path, dev_idx=dev_idx, connection=connection, pid=pid) as tr:
            ver = tr.ping(timeout=0.35)
            name = ""
            model_id = ""
            try:
                name = tr.get_device_name()
            except HidppError:
                pass
            try:
                model_id = tr.get_model_id_hex()
            except HidppError:
                pass

            if require_g715:
                is_g715 = (
                    "g715" in name.lower()
                    or "C347" in model_id
                    or "40A2" in model_id
                    or "B368" in model_id
                )
                if not is_g715:
                    return None

            return DeviceCandidate(
                hidraw_path=dev_path,
                vid=vid,
                pid=pid,
                hid_name=hid_name,
                connection=connection,
                dev_idx=dev_idx,
                device_name=name or hid_name or "Logitech G715",
                protocol_version=f"{ver[0]}.{ver[1]}",
            )
    except HidppError:
        return None
