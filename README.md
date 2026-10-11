# MFU Helmet Safety Entry-System - Setup Guide

Pipeline: Camera -> Python/OpenCV -> custom YOLO -> MQTT (HiveMQ) -> Node-RED -> MQTT -> ESP32 -> servo barrier

## Files
| File | Purpose |
|---|---|
| `train_model.py` | Trains the custom YOLO model (lab workflow) |
| `split_dataset.py` | Moves 20% of labelled images to `val` |
| `custom_dataset/dataset.yaml` | Class + path config (`helmet`, `no_helmet`) |
| `helmet_detect.py` | Live detection, debounce, MQTT publish, violation snapshots |
| `simulate_event.py` | Fake SAFE/VIOLATION events to test Node-RED + ESP32 without a camera |
| `nodered_flow.json` | Importable Node-RED flow + dashboard + SQLite logging |
| `esp32_barrier/esp32_barrier.ino` | ESP32 servo firmware |

## MQTT topics (prefix `mfu-helmet-6731502018` - change it everywhere if you want your own)
| Topic | Direction | Payload |
|---|---|---|
| `<prefix>/event` | Python -> Node-RED | `{"status":"SAFE\|VIOLATION\|NONE","confidence":0.93,"timestamp":"...","camera_id":"gate-1","image":"violations/x.jpg"}` |
| `<prefix>/cmd` | Node-RED -> ESP32 | `OPEN` or `CLOSE` |
| `<prefix>/status` | ESP32 -> Node-RED | `OPEN`, `CLOSED`, `OFFLINE` (retained) |

## Step 1 - Install
```
pip install -r requirements.txt
```
Node-RED: install Node.js, then `npm install -g node-red`, run `node-red`, open http://localhost:1880.
Palette Manager -> install `node-red-dashboard` and `node-red-node-sqlite`.

## Step 2 - Broker
Quickest: public broker `broker.hivemq.com` port 1883 (no login; keep the unique topic prefix).
Better for the report/demo: free HiveMQ Cloud cluster -> create credentials -> use port 8883 with TLS, then:
- Python: set `MQTT_HOST`, `MQTT_PORT=8883`, `MQTT_TLS=1`, `MQTT_USER`, `MQTT_PASS` environment variables
- ESP32: edit `MQTT_HOST`, `MQTT_PORT`, `USE_TLS=true`, user, password
- Node-RED: edit the HiveMQ broker node (Security tab for login, Connection tab -> enable TLS)

## Step 3 - Build the dataset (class order: helmet first, no_helmet second)
1. Take 300-500 photos of you and your teammate with the helmet ON and OFF: different angles, distances, lighting, backgrounds, helmet colours, glasses/caps if possible. Optionally add rider photos at the gate.
2. Put all photos in `custom_dataset/images/train/`. Create empty `custom_dataset/images/val`, `custom_dataset/labels/train`, `custom_dataset/labels/val`.
3. `labelImg` -> Open Dir (images/train), Change Save Dir (labels/train), choose **YOLO** format. Draw a box around the head+helmet (class `helmet`) or the bare head (class `no_helmet`). Label the first image `helmet` first so `classes.txt` order is helmet=0, no_helmet=1.
4. `python split_dataset.py` (checks only labelled images are moved). Confirm both classes exist in val.
5. Download `yolo11n.pt` into `custom_dataset/model/`.

## Step 4 - Train
```
python train_model.py
```
Best weights: `custom_dataset/runs/detect/custom_model/train_result/weights/best.pt`.
Take screenshots of `results.png`, `confusion_matrix.png`, and note mAP50 / precision / recall for the report. If weak: add more images, balance both classes, train longer.

## Step 5 - Node-RED
Menu -> Import -> select `nodered_flow.json` -> Deploy. Dashboard: http://localhost:1880/ui
Check the SQLite node's database path (`helmet_violations.db`) is writable (use an absolute path if needed).

## Step 6 - ESP32
Arduino IDE -> install ESP32 board support, libraries **PubSubClient** and **ESP32Servo**. Edit WiFi/MQTT settings in `esp32_barrier.ino`, upload, open Serial Monitor at 115200.
Wiring: servo signal -> GPIO18, servo power -> 5V/VIN (use an external 5V supply if the servo jitters; connect grounds together), servo GND -> GND. Tune `OPEN_ANGLE` / `CLOSED_ANGLE`.

## Step 7 - Test (do this before the real camera)
1. `python simulate_event.py VIOLATION` -> dashboard turns red, barrier closes, a row is added to the DB, count increases.
2. `python simulate_event.py SAFE` -> dashboard green, barrier opens.
3. Run `python helmet_detect.py`: helmet on -> SAFE, helmet off -> VIOLATION. Press `q` to quit.
Tune `CONF_THRES` (default 0.50) and `CONFIRM_FRAMES` (default 5) via environment variables if it flickers.

## Troubleshooting
- No camera: change `CAM_INDEX` (0, 1, 2).
- Nothing reaches Node-RED: topic prefix must be identical in Python, Node-RED and ESP32; check the debug sidebar.
- ESP32 `rc=-2`/`-4`: wrong host/port or TLS setting; `rc=5`: bad credentials.
- Servo resets the ESP32: power the servo from a separate 5V supply with shared ground.
- Model confuses classes: confirm `dataset.yaml` names order matches `classes.txt`.
- Do not commit broker passwords to GitHub.

## Demo notes
Keep the camera fixed, well lit, and 0.5-1.5 m away. Show the dashboard, the Python window and the barrier together. Mention privacy: violation snapshots contain faces, so store them securely and only for review.
