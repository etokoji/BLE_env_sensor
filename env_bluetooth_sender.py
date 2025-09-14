import bluetooth
from time import sleep
import time

# Constants for this environment
BT_DEVICE_NAME = "EtoSense"


class EnvBluetoothSender:
    """BLE advertiser that embeds measurement data into the advertising packet.

    API used by read_sensors.measure_and_send:
      - setup_bluetooth()
      - advertise_payload(data_bytes: bytes, duration_sec: int) -> bool

    Note: Legacy advertising payload has max 31 bytes. Keep data compact.
    """

    def __init__(self):
        self.ble = None

    def setup_bluetooth(self):
        # Activate BLE and be ready to advertise
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        return True

    def _build_adv(self, name: str, mfg_bytes: bytes) -> bytes:
        # AD structures: Flags (0x01), Complete Local Name (0x09) or Shortened Local Name (0x08),
        # Manufacturer Specific (0xFF). Ensure final adv <= 31 bytes.
        COMPANY_ID = b"\xff\xff"
        flags = bytes([0x02, 0x01, 0x06])
        name_b = name.encode() if name else b""

        # Manufacturer payload always starts with COMPANY_ID
        full_mfg_payload = COMPANY_ID + (mfg_bytes or b"")
        full_mfg_ad = bytes([len(full_mfg_payload) + 1, 0xFF]) + full_mfg_payload

        # Try full name + full mfg
        if name_b:
            full_name_ad = bytes([len(name_b) + 1, 0x09]) + name_b
            adv = flags + full_name_ad + full_mfg_ad
            if len(adv) <= 31:
                return adv

        # If too large, try shortened name (0x08) truncated to fit while keeping full mfg if possible
        max_name_b_len = (
            31 - len(flags) - len(full_mfg_ad) - 2
        )  # -2 for AD header (len + type)
        if name_b and max_name_b_len > 0:
            name_trim = name_b[:max_name_b_len]
            short_name_ad = bytes([len(name_trim) + 1, 0x08]) + name_trim
            adv = flags + short_name_ad + full_mfg_ad
            if len(adv) <= 31:
                return adv

        # Otherwise, preserve as much manufacturer payload as possible (include COMPANY_ID)
        max_payload_len = (
            31 - len(flags) - 2
        )  # available bytes for payload (excluding len/type)
        payload_trim = full_mfg_payload[:max_payload_len]
        mfg_ad = bytes([len(payload_trim) + 1, 0xFF]) + payload_trim
        adv = flags + mfg_ad
        return adv

    def advertise_payload(
        self, data_bytes: bytes, duration_sec: int = 5, interval_ms: int = 50
    ):
        if isinstance(data_bytes, str):
            data_bytes = data_bytes.encode()
        adv_data = self._build_adv(BT_DEVICE_NAME, data_bytes)
        try:
            self.ble.gap_advertise(interval_ms, adv_data)
            # Broadcast for duration then stop (use time-based loop for accuracy and early-exit)
            start_ms = time.ticks_ms()
            duration_ms = int(duration_sec * 1000)
            while time.ticks_diff(time.ticks_ms(), start_ms) < duration_ms:
                # small sleep to avoid busy-wait and allow responsiveness
                sleep(0.1)
                # optional: check for a cancel flag here (e.g. if hasattr(self, 'stop_now') and self.stop_now: break)
            self.ble.gap_advertise(None)
            return True
        except Exception as e:
            try:
                print("Advertise error:", e)
            except:
                pass
            try:
                self.ble.gap_advertise(None)
            except Exception:
                pass
            return False

