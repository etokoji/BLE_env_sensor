import machine
import ujson
from machine import Pin
from time import sleep, sleep_ms

import read_sensors
from env_bluetooth_sender import EnvBluetoothSender


SleepTimeInMs = 1000*20 - 605  # 60 - 0.605 sec
#SleepTimeInMs = 1000*15 - 605  # 15 - 0.605 sec

DEV_ID = 10

# ESP32-C3のMODEボタン（通常GPIO9）
MODE_PIN = 9
LED_PIN = 8

# I2C
# SCL = 10
# SDA = 7

def is_mode_button_pressed():
    """MODEボタンの状態をチェック"""
    mode_pin = Pin(MODE_PIN, Pin.IN, Pin.PULL_UP)
    sleep_ms(50)  # 安定化待機
    return mode_pin.value() == 0  # LOW = 押下


# ESP32-C3 IO2は、電源投入時にHになるので使えない。
DONE_PIN = 4
done_pin = Pin(DONE_PIN, Pin.OUT)
done_pin.off()

def get_rtc_data():
    rtc = machine.RTC()
    
    try:
        # RTCメモリからデータを読み込む
        memory_content = rtc.memory()
        
        if not memory_content:  # メモリが空の場合
            print("RTCメモリが空です")
            return None
        
        # JSONデータをデコード
        stored_data = ujson.loads(memory_content)
        return stored_data
    
    except ValueError as e:
        # JSONデコードエラーの処理
        print(f"JSONデコードエラー: {e}")
        return None
    
    except Exception as e:
        # その他の予期せぬエラーの処理
        print(f"予期せぬエラーが発生しました: {e}")
        return None
    
def save_rtc_data(data):
    rtc = machine.RTC()
    rtc.memory(ujson.dumps(data).encode())

def main():

    stored_data = get_rtc_data()
    
    if stored_data is not None:
        print(stored_data)
        
    else:
        stored_data = { "r_id": 1 }
        save_rtc_data(stored_data)
        
    r_id = stored_data["r_id"]
    
    
    if is_mode_button_pressed():
        return
    
    print(f'boot reason: {machine.reset_cause()}')
    if machine.reset_cause() == machine.HARD_RESET:
        print("hard resetからの起動です")
        sleep(10)
    else:
        if machine.reset_cause() == machine.DEEPSLEEP_RESET:
            print("deep sleepからの起動です")

        # Bluetoothセンダーを初期化
        bt_sender = EnvBluetoothSender()
        bt_sender.setup_bluetooth()
        
        # センサーデータの測定と送信
        success = read_sensors.measure_and_send(DEV_ID, r_id, bt_sender)
        
        if success:
            stored_data["r_id"] = r_id + 1
            save_rtc_data(stored_data)
        else:
            print("Failed to send data, keeping same r_id for retry")

        print("going to power down")
        sleep(0.2)
        done_pin.on()
        # power goes off here -----
        
        
        print('Going to deep sleep...')
        machine.deepsleep(SleepTimeInMs)
        #print('Going to light sleep...')
        #machine.lightsleep(15000)


if __name__ == '__main__':
    main()

