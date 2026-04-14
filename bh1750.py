"""
BH1750FVI 環境光センサー (I2C) — MicroPython

接続例:
  VCC → 3.3V
  GND → GND
  SDA → ボードの I2C SDA
  SCL → ボードの I2C SCL
  ADDR 未接続または GND → アドレス 0x23
  ADDR → VCC → アドレス 0x5C
"""

from micropython import const
import time

POWER_DOWN = const(0x00)
POWER_ON = const(0x01)
RESET = const(0x07)

# 連続測定
CONT_H_RES = const(0x10)  # 1 lx, 典型 120 ms
CONT_H_RES2 = const(0x11)  # 0.5 lx, 典型 120 ms
CONT_L_RES = const(0x13)  # 4 lx, 典型 16 ms

# ワンショット (読み取りのたびにコマンド送信)
ONE_H_RES = const(0x20)
ONE_H_RES2 = const(0x21)
ONE_L_RES = const(0x23)

ADDR_GND = const(0x23)
ADDR_VCC = const(0x5C)


class BH1750:
    def __init__(self, i2c, addr=ADDR_GND, mode=CONT_H_RES):
        self.i2c = i2c
        self.addr = addr
        self._mode = mode
        self._delay_ms = self._measure_delay_ms(mode)
        self._lux_div = self._lux_divisor(mode)

    @staticmethod
    def _measure_delay_ms(mode):
        if mode in (CONT_L_RES, ONE_L_RES):
            return 24  # 16 ms 典型 + 余裕
        return 180  # 120 ms 典型 + 余裕

    @staticmethod
    def _lux_divisor(mode):
        # H-res mode2 は感度 2 倍 → lux は raw / 2.4
        if mode in (CONT_H_RES2, ONE_H_RES2):
            return 2.4
        return 1.2

    def reset(self):
        self.i2c.writeto(self.addr, bytes([POWER_ON]))
        time.sleep_ms(10)
        self.i2c.writeto(self.addr, bytes([RESET]))

    def configure(self, mode=None):
        """測定モードを設定し、電源オンして測定を開始する。"""
        if mode is not None:
            self._mode = mode
            self._delay_ms = self._measure_delay_ms(mode)
            self._lux_div = self._lux_divisor(mode)
        self.i2c.writeto(self.addr, bytes([POWER_ON]))
        time.sleep_ms(10)
        self.i2c.writeto(self.addr, bytes([self._mode]))
        time.sleep_ms(self._delay_ms)

    def raw(self):
        """現在の生データ (0–65535 付近) を返す。"""
        data = self.i2c.readfrom(self.addr, 2)
        return (data[0] << 8) | data[1]

    def lux(self):
        """照度 [lx] を返す。連続モードでは configure 後に繰り返し呼べる。"""
        time.sleep_ms(self._delay_ms)
        return self.raw() / self._lux_div

    def measure_lux(self, mode=None):
        """ワンショット: 測定して lx を返す (mode に ONE_* を推奨)。"""
        if mode is not None:
            self._mode = mode
            self._delay_ms = self._measure_delay_ms(mode)
            self._lux_div = self._lux_divisor(mode)
        self.i2c.writeto(self.addr, bytes([POWER_ON]))
        time.sleep_ms(10)
        self.i2c.writeto(self.addr, bytes([self._mode]))
        time.sleep_ms(self._delay_ms)
        return self.raw() / self._lux_div

    def power_down(self):
        self.i2c.writeto(self.addr, bytes([POWER_DOWN]))


__all__ = [
    "BH1750",
    "POWER_DOWN",
    "POWER_ON",
    "RESET",
    "CONT_H_RES",
    "CONT_H_RES2",
    "CONT_L_RES",
    "ONE_H_RES",
    "ONE_H_RES2",
    "ONE_L_RES",
    "ADDR_GND",
    "ADDR_VCC",
]
