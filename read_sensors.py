from machine import Pin, SoftI2C, ADC
from time import sleep, sleep_us
import ujson
import struct

import BME280
import AHT10


SCL = 9
SDA = 8

ADC_PIN = 0
ADC_EN = 1

ADC_COF = 0.001090467


def setup_i2c():
    #  I2C設定
    p21 = Pin(SDA, Pin.IN, Pin.PULL_UP)
    p22 = Pin(SCL, Pin.IN, Pin.PULL_UP)

    i2c = SoftI2C(scl=Pin(SCL), sda=Pin(SDA), freq=10000)

    print("i2c setup")

    return i2c


def setup_ADC():
    # ADCピンの設定 (例: Pin 34)
    adc = ADC(Pin(ADC_PIN))
    adc_enable = Pin(ADC_EN, Pin.OUT)
    adc_enable.off()

    # ADCの幅を設定 (9ビット、10ビット、11ビット、12ビットのいずれか)
    adc.width(ADC.WIDTH_12BIT)

    # 測定範囲を設定 (0～1V、0～3.3Vなど)
    #adc.atten(ADC.ATTN_2_5DB)  # 0-3.3Vの範囲
    adc.atten(ADC.ATTN_11DB)  # 0-3.3Vの範囲
    

    return adc, adc_enable


def read_ADC():
    # 10回ADCの値を読み取って合計
    adc_enable.on()  #  分圧抵抗に電流を流す
    #sleep_us(50)
    
    count = 10
    total = 0
    for _ in range(count):
        adc_value = adc.read()
        print(f"val={adc_value}")
        total += adc_value
        sleep_us(20)  #  (必要に応じて調整)   短くするとなぜかADCの値が大きくなる。

    adc_enable.off() #  分圧抵抗の電流を止める
    
    # 平均値を計算
    average_value = total // count
    
    #  実際の電源電圧に変換
    conv_value = average_value * ADC_COF
    
    # 平均値を出力
    print(f"Average ADC Value: {conv_value:.3f}V ({average_value})")
    
    return conv_value


def read_bme280(i2c):

    bme = BME280.BME280(i2c=i2c)
    temp_s = bme.temperature
    hum_s = bme.humidity
    
    # pressureプロパティを使用して正しくスケーリング
    # pressureプロパティは "XX.XX" 形式の文字列を返す（hPa単位）
    pres_hpa_str = bme.pressure
    pres_hpa = float(pres_hpa_str)
    pres_pa = pres_hpa * 100.0  # hPaからPaへ変換

    #pres = 0.0
    # uncomment for temperature in Fahrenheit
    # temp = (bme.read_temperature()/100) * (9/5) + 32
    # temp = str(round(temp, 2)) + 'F'
    #     print('Temperature: ', temp_s)
    #     print('Humidity: ', hum_s)

    temp = float(temp_s)
    hum = float(hum_s)
    pres = pres_pa  # パスカル単位で返す

    return temp, hum, pres


def read_aht10(i2c):
    # AHT10センサーのインスタンス化
    aht10 = AHT10.AHT10(i2c)
    hum, temp = aht10.measure()

    return temp, hum


# JSON文字列データ（従来方式）
def create_struct_message(dev_id, temp, hum, pres, vdd, reading_id):
    message = {
        "device_id": dev_id,
        "temperature": temp,
        "humidity": hum,
        "pressure": pres,
        "vdd": vdd,
        "reading_id": reading_id,
    }
    return ujson.dumps(message)


# アドバタイジングに載せる軽量バイナリ（Manufacturer Specific Data）
# フォーマット: b'ENV' + dev_id(u1) + r_id(u2) + temp(dC i2) + hum(d% u2) + pres(hPa u2) + vdd(cV u2)
# 単位: 温度0.1°C, 湿度0.1%, 気圧0.1hPa, 電圧0.01V
# 合計: 3 + 1 + 2 + 2 + 2 + 2 + 2 = 14 bytes


def build_adv_measure_payload(dev_id, reading_id, temp_c, hum_pct, pres_pa, vdd_v):
    hdr = b"ENV"
    t_dC = int(round(temp_c * 10))  # signed int16
    h_dP = int(round(hum_pct * 10))  # unsigned int16
    # 気圧をhPa単位に変換してから10倍（0.1hPa精度）
    p_hPa_x10 = int(round((pres_pa / 100.0) * 10))  # Pa → hPa → 0.1hPa単位
    v_cV = int(round(vdd_v * 100))  # unsigned int16
    return hdr + struct.pack(
        ">BHhHHH", dev_id & 0xFF, reading_id & 0xFFFF, t_dC, h_dP & 0xFFFF, p_hPa_x10 & 0xFFFF, v_cV & 0xFFFF
    )


def measure_and_send(dev_id, r_id, bt_sender):

    vdd = read_ADC()

    pres = 0.0
    
    # BME280から気圧データを取得を試行、失敗時はデフォルト値を使用
    try:
        temp_bme, hum_bme, pres = read_bme280(i2c)
        print(f"BME280: temp={temp_bme:.1f}°C, hum={hum_bme:.1f}%, pres={pres:.1f}Pa")
    except Exception as e:
        print(f"BME280 error: {e}")
        print("Using pressure default value: 0.0")
        pres = 0.0
    
    # AHT10から温度・湿度データを取得（こちらを優先使用）
    temp, hum = read_aht10(i2c)

    print("DEV_ID", dev_id)
    print("r_id", r_id)
    print(f"temp: {temp}, humidity:{hum}")
    print(f"湿度: {hum:.1f}%, 温度: {temp:.1f}°C,  気圧: {pres:.3f}")

    # 広告用の軽量バイナリに変換して一定時間アドバタイズ
    adv_payload = build_adv_measure_payload(dev_id, r_id, temp, hum, pres, vdd)
    ret = False
    try:
        # 省電力のため短時間でアドバタイジング
        ret = bt_sender.advertise_payload(adv_payload, duration_sec=0.11, interval_ms=25)
    except Exception as e:
        print("advertise exception:", e)
        ret = False

    return ret


# ----

led = Pin(8, Pin.OUT)
led.off()
sleep(0.2)
led.on()

i2c = setup_i2c()
adc, adc_enable = setup_ADC()

