"""
Test Node-RED + ESP32 without a camera/model.
Usage:  python simulate_event.py SAFE
        python simulate_event.py VIOLATION
"""
import json
import os
import sys
import time
from datetime import datetime

import paho.mqtt.client as mqtt

status = (sys.argv[1] if len(sys.argv) > 1 else "VIOLATION").upper()
host = os.getenv("MQTT_HOST", "broker.hivemq.com")
port = int(os.getenv("MQTT_PORT", "1883"))
prefix = os.getenv("TOPIC_PREFIX", "mfu-helmet-6731502018")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sim-{int(time.time())}")
if os.getenv("MQTT_USER"):
    client.username_pw_set(os.getenv("MQTT_USER"), os.getenv("MQTT_PASS", ""))
if os.getenv("MQTT_TLS", "0") == "1":
    client.tls_set()
client.connect(host, port, 30)
client.loop_start()

payload = {
    "status": status,
    "confidence": 0.91,
    "timestamp": datetime.now().isoformat(timespec="seconds"),
    "camera_id": "gate-1",
    "image": "",
}
info = client.publish(f"{prefix}/event", json.dumps(payload), qos=1)
info.wait_for_publish()
print("Published:", payload)
client.loop_stop()
client.disconnect()
