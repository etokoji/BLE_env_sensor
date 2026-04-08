#
# このファイル(bluetooth_sender.py)は現在未使用 → BLEサービス方式の送信クラス（旧版）
"""
Reusable BLE Sender class for MicroPython on ESP32.

- Based on experiment/bluetooth_ultra_fast_sender.py
- Exposes a simple class you can import and use from other modules
- Focused on fast connect-read-disconnect cycles

Example usage (on ESP32 REPL):

    from bluetooth_sender import BLESender
    import ujson

    sender = BLESender(
        service_uuid="0fa17253-af0a-4301-b84a-b45ec29b7183",
        characteristic_uuid="B01679E9-807A-4CB2-8B73-9f37c963D184",
        device_name="ESP32_Sensor",
        adv_interval_ms=20,
    )

    if sender.setup():
        # Prepare JSON data and write to GATT
        data = {
            "device_id": "esp32_ultra",
            "temperature": 22.5,
            "humidity": 57.0,
            "pressure": 1013.25,
            "vdd": 3.30,
            "reading_id": 1,
            "method": "ultra_fast",
        }
        sender.send_json(data)

        # Wait for a central to connect, read, then disconnect
        if sender.wait_for_connection(timeout_sec=15):
            sender.wait_for_read_and_disconnect(timeout_sec=5)

        sender.deactivate()

"""

import bluetooth
import ubinascii
import ujson
from time import sleep


class BLESender:
    def __init__(self,
                 service_uuid,
                 characteristic_uuid,
                 device_name="ESP32_Sensor",
                 adv_interval_ms=20):
        """Create a reusable BLE GATT sender.

        Args:
            service_uuid (str|bluetooth.UUID): Service UUID (str or bluetooth.UUID)
            characteristic_uuid (str|bluetooth.UUID): Characteristic UUID
            device_name (str): GAP device name used for advertising
            adv_interval_ms (int): Advertising interval in ms (e.g., 20 for ultra-fast)
        """
        # Normalize UUIDs
        self.SERVICE_UUID = bluetooth.UUID(service_uuid) if not isinstance(service_uuid, bluetooth.UUID) else service_uuid
        self.CHAR_UUID = bluetooth.UUID(characteristic_uuid) if not isinstance(characteristic_uuid, bluetooth.UUID) else characteristic_uuid

        # GAP settings
        self.device_name = device_name
        self.adv_interval_ms = adv_interval_ms

        # BLE state
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self._irq)

        self.connected = False
        self.conn_handle = None

        # GATT handles (value handle for the characteristic)
        self.value_handle = None

        # Data buffer
        self.current_data = b""
        self.data_sent = False
        self.read_requests = 0
        self.first_read_time = None

    # ---------- Public API ----------

    def setup(self):
        """Register service/characteristic and start advertising.
        Returns True on success, False on failure.
        """
        try:
            service = (
                self.SERVICE_UUID,
                (
                    (self.CHAR_UUID, bluetooth.FLAG_READ | bluetooth.FLAG_WRITE),
                ),
            )

            services = (service,)
            result = self.ble.gatts_register_services(services)

            # Extract value handle from registration result
            # Expected shape (per MicroPython): ((value_handle, ...), ...)
            if isinstance(result, tuple) and len(result) > 0:
                if isinstance(result[0], tuple) and len(result[0]) > 0:
                    self.value_handle = result[0][0]
                else:
                    raise Exception("Unexpected registration result format")
            else:
                raise Exception("Service registration failed")

            self.start_advertising()
            return True
        except Exception as e:
            try:
                print("BLE setup error:", e)
            except:
                pass
            return False

    def start_advertising(self):
        """Begin GAP advertising with the configured device name and interval."""
        try:
            flags = bytes([0x02, 0x01, 0x06])
            name = self.device_name.encode()
            name_data = bytes([len(name) + 1, 0x09]) + name
            adv_data = flags + name_data
            self.ble.gap_advertise(self.adv_interval_ms, adv_data)
        except Exception as e:
            try:
                print("Advertising error:", e)
            except:
                pass

    def stop_advertising(self):
        """Stop GAP advertising."""
        try:
            self.ble.gap_advertise(None)
        except Exception:
            pass

    def set_payload(self, data_bytes):
        """Set raw payload bytes into the characteristic value.
        Also writes to the local GATT db so a central can read it immediately.
        """
        if isinstance(data_bytes, str):
            data_bytes = data_bytes.encode('utf-8')
        self.current_data = data_bytes
        try:
            if self.value_handle is not None and self.current_data:
                self.ble.gatts_write(self.value_handle, self.current_data)
        except Exception as e:
            try:
                print("GATT write error:", e)
            except:
                pass

    def send_json(self, obj):
        """Serialize obj to JSON and set as payload."""
        try:
            text = ujson.dumps(obj)
            self.set_payload(text)
        except Exception as e:
            try:
                print("JSON encode error:", e)
            except:
                pass

    def wait_for_connection(self, timeout_sec=15):
        """Wait until connected or timeout. Returns True if connected."""
        count = 0
        self.data_sent = False
        self.read_requests = 0
        self.first_read_time = None
        while not self.connected and count < timeout_sec * 20:
            sleep(0.05)
            count += 1
        return self.connected

    def wait_for_read_and_disconnect(self, timeout_sec=5):
        """Wait for a central read request, then auto-disconnect quickly.
        Returns True if data was read and disconnect occurred (natural or forced).
        """
        count = 0
        while self.connected and count < timeout_sec * 20:
            sleep(0.05)
            count += 1
            if self.data_sent:
                # brief window for natural disconnect
                mini = 2  # ~100ms
                for _ in range(mini):
                    if not self.connected:
                        return True
                    sleep(0.05)
                # force stop advertising to nudge disconnect
                self.stop_advertising()
                # wait briefly for disconnect
                for _ in range(10):  # ~500ms
                    if not self.connected:
                        return True
                    sleep(0.05)
                return self.data_sent
        return self.data_sent

    def deactivate(self):
        """Turn off BLE radio."""
        try:
            self.stop_advertising()
            self.ble.active(False)
        except Exception:
            pass

    # ---------- Internal IRQ ----------

    def _irq(self, event, data):
        try:
            if event == 1:  # _IRQ_CENTRAL_CONNECT
                self.conn_handle, addr_type, addr = data
                self.connected = True
                self.data_sent = False
                self.read_requests = 0
                self.first_read_time = None
                try:
                    print("Connect:", ubinascii.hexlify(addr).decode())
                except Exception:
                    pass

            elif event == 2:  # _IRQ_CENTRAL_DISCONNECT
                self.conn_handle, addr_type, addr = data
                self.connected = False
                try:
                    print("Disconnect:", ubinascii.hexlify(addr).decode())
                except Exception:
                    pass

            elif event == 4:  # _IRQ_GATTS_READ_REQUEST
                conn_handle, attr_handle = data
                self.read_requests += 1
                if self.first_read_time is None:
                    try:
                        import time
                        self.first_read_time = time.ticks_ms()
                    except Exception:
                        pass
                if self.value_handle is not None and attr_handle == self.value_handle:
                    if self.current_data and not self.data_sent:
                        self.data_sent = True
        except Exception:
            # Keep IRQ minimal and robust
            pass

