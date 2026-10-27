
import network
import time

import config


def connect_wifi(timeout_s=20):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        print("Wi-Fi already connected:", wlan.ifconfig()[0])
        return wlan

    print("Connecting to Wi-Fi...")
    wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)

    start = time.ticks_ms()

    while not wlan.isconnected():
        if time.ticks_diff(time.ticks_ms(), start) > timeout_s * 1000:
            raise RuntimeError("Wi-Fi connection timed out")
        time.sleep_ms(250)

    print("Wi-Fi connected:", wlan.ifconfig()[0])
    return wlan
