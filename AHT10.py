from machine import I2C, Pin
import time

# AHT10のI2Cアドレス
AHT10_ADDR = 0x38

# AHT10コマンド
AHT10_INIT = 0xE1
AHT10_MEASURE = 0xAC

class AHT10:
    def __init__(self, i2c, address=AHT10_ADDR):
        self.i2c = i2c
        self.address = address
        self.init_sensor()

    def init_sensor(self):
        self.i2c.writeto(self.address, bytes([AHT10_INIT, 0x08, 0x00]))
        time.sleep_ms(100)

    def measure(self):
        self.i2c.writeto(self.address, bytes([AHT10_MEASURE, 0x33, 0x00]))
        time.sleep_ms(100)
        data = self.i2c.readfrom(self.address, 6)
        
        humidity = (data[1] << 12) | (data[2] << 4) | (data[3] >> 4)
        humidity = (humidity / 1048576) * 100
        
        temp = ((data[3] & 0x0F) << 16) | (data[4] << 8) | data[5]
        temp = ((temp / 1048576) * 200) - 50
        
        return humidity, temp
    