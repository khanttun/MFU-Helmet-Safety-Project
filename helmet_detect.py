```python
"""
MFU Helmet Safety Entry-System
Camera -> YOLO (helmet / no_helmet) -> MQTT (HiveMQ)
       -> SQLite Database -> Flask MJPEG Video Stream

Run:  python helmet_detect.py
Quit: press 'q' in the camera window
"""

import json
import os
import threading
import time
import sqlite3
from datetime import datetime

import cv2
from flask import Flask, Response
import paho.mqtt.client as mqtt
from ultralytics import YOLO


# ---------------- Configuration ----------------

MODEL_PATH = os.getenv("MODEL_PATH", "best.pt")
CAM_INDEX = int(os.getenv("CAM_INDEX", "0"))
CONF_THRES = float(os.getenv("CONF_THRES", "0.30"))
CONFIRM_FRAMES = int(os.getenv("CONFIRM_FRAMES", "3"))

SHOW_WINDOW = os.getenv("SHOW_WINDOW", "1") == "1"
STREAM_ENABLED = os.getenv("STREAM", "1") == "1"
STREAM_PORT = int(os.getenv("STREAM_PORT", "5000"))

DB_PATH = os.getenv("DB_PATH", "helmet_events.db")

MQTT_HOST = os.getenv("MQTT_HOST", "broker.hivemq.com")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TLS = os.getenv("MQTT_TLS", "0") == "1"
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")

TOPIC_PREFIX = os.getenv(
    "TOPIC_PREFIX", "mfu-helmet-6731502018"
)
TOPIC_EVENT = f"{TOPIC_PREFIX}/event"

CAMERA_ID = os.getenv("CAMERA_ID", "gate-1")

SNAPSHOT_DIR = "violations"
os.makedirs(SNAPSHOT_DIR, exist_ok=True)


# ---------------- SQLite Database ----------------

def init_database():
    """Create the database and event table if they do not exist."""

    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS helmet_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL,
                confidence REAL NOT NULL,
                timestamp TEXT NOT NULL,
                camera_id TEXT NOT NULL,
                image TEXT
            )
        """)

    print(f"[DB] Database initialized: {DB_PATH}")


def save_event(status, confidence, timestamp, image_path=""):
    """Save one confirmed detection event to SQLite."""

    try:
        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            conn.execute("""
                INSERT INTO helmet_events
                (status, confidence, timestamp, camera_id, image)
                VALUES (?, ?, ?, ?, ?)
            """, (
                status,
                round(float(confidence), 3),
                timestamp,
                CAMERA_ID,
                image_path
            ))

        print(f"[DB] Saved event: {status}")

    except sqlite3.Error as error:
        print(f"[DB ERROR] Could not save event: {error}")


# ---------------- MQTT ----------------

def make_client():
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"helmet-detector-{int(time.time())}",
    )

    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)

    if MQTT_TLS:
        client.tls_set()

    def on_connect(client, userdata, flags, reason_code, properties):
        print(f"[MQTT] Connection result: {reason_code}")

    def on_disconnect(
        client, userdata, disconnect_flags,
        reason_code, properties
    ):
        print(f"[MQTT] Disconnected: {reason_code}")

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    client.connect_async(
        MQTT_HOST,
        MQTT_PORT,
        keepalive=30
    )
    client.loop_start()

    return client


def publish_event(
    client, status, confidence, timestamp, image_path=""
):
    """Publish an event to HiveMQ."""

    payload = {
        "status": status,
        "confidence": round(float(confidence), 3),
        "timestamp": timestamp,
        "camera_id": CAMERA_ID,
        "image": image_path,
    }

    info = client.publish(
        TOPIC_EVENT,
        json.dumps(payload),
        qos=1,
    )

    print(f"[MQTT] Published event: {payload}")
    return info


# ---------------- Video Stream ----------------

_latest_jpeg = None
_frame_lock = threading.Lock()
_stream_app = Flask(__name__)


def publish_frame(frame):
    """Store the newest annotated frame for the video stream."""

    global _latest_jpeg

    if not STREAM_ENABLED:
        return

    ok, buf = cv2.imencode(
        ".jpg",
        frame,
        [cv2.IMWRITE_JPEG_QUALITY, 70]
    )

    if ok:
        with _frame_lock:
            _latest_jpeg = buf.tobytes()


def _mjpeg_generator():
    while True:
        with _frame_lock:
            jpeg = _latest_jpeg

        if jpeg is None:
            time.sleep(0.05)
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n"
            + jpeg
            + b"\r\n"
        )

        time.sleep(0.04)


@_stream_app.route("/video_feed")
def video_feed():
    return Response(
        _mjpeg_generator(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


def start_stream_server():
    if not STREAM_ENABLED:
        return

    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    threading.Thread(
        target=lambda: _stream_app.run(
            host="0.0.0.0",
            port=STREAM_PORT,
            threaded=True,
            debug=False,
            use_reloader=False,
        ),
        daemon=True,
    ).start()

    print(
        f"[STREAM] http://localhost:{STREAM_PORT}/video_feed"
    )


# ---------------- Detection Logic ----------------

def classify(result, names):
    """
    Class names expected: helmet and no_helmet.
    Returns SAFE, VIOLATION, or NONE.
    """

    helmet_conf = 0.0
    no_helmet_conf = 0.0

    for box in result.boxes:
        class_id = int(box.cls[0])
        confidence = float(box.conf[0])

        name = str(names[class_id]).lower().strip()
        name = name.replace(" ", "_").replace("-", "_")

        if name == "helmet":
            helmet_conf = max(helmet_conf, confidence)

        elif name in ("no_helmet", "nohelmet"):
            no_helmet_conf = max(no_helmet_conf, confidence)

    print(
        f"\r[DETECTIONS] helmet={helmet_conf:.2f} | "
        f"no_helmet={no_helmet_conf:.2f}     ",
        end="",
        flush=True,
    )

    if helmet_conf == 0.0 and no_helmet_conf == 0.0:
        return "NONE", 0.0

    if helmet_conf > 0.0 and no_helmet_conf > 0.0:
        if helmet_conf > no_helmet_conf:
            return "SAFE", helmet_conf

        elif no_helmet_conf > helmet_conf:
            return "VIOLATION", no_helmet_conf

        else:
            return "NONE", helmet_conf

    if helmet_conf > 0.0:
        return "SAFE", helmet_conf

    return "VIOLATION", no_helmet_conf


# ---------------- Main Program ----------------

def main():
    init_database()

    print(f"[MODEL] Loading {MODEL_PATH}...")
    model = YOLO(MODEL_PATH)

    print("[MODEL] Classes:", model.names)

    class_names = [
        str(name).lower().strip().replace(" ", "_").replace("-", "_")
        for name in model.names.values()
    ]

    if (
        "helmet" not in class_names
        or not any(
            name in ("no_helmet", "nohelmet")
            for name in class_names
        )
    ):
        raise SystemExit(
            "[ERROR] Model must contain both 'helmet' "
            "and 'no_helmet' classes. Check best.pt."
        )

    print("[MODEL] Helmet classes verified.")

    client = make_client()
    start_stream_server()

    cap = cv2.VideoCapture(CAM_INDEX)

    if not cap.isOpened():
        client.loop_stop()
        client.disconnect()
        raise SystemExit(
            f"[ERROR] Cannot open camera index {CAM_INDEX}"
        )

    current_state = "NONE"
    candidate = "NONE"
    streak = 0

    colors = {
        "SAFE": (0, 200, 0),
        "VIOLATION": (0, 0, 255),
        "NONE": (150, 150, 150),
    }

    print("[CAMERA] Started. Press 'q' to quit.")

    try:
        while True:
            ok, frame = cap.read()

            if not ok:
                print("\n[ERROR] Camera read failed.")
                break

            result = model(
                frame,
                conf=CONF_THRES,
                verbose=False,
            )[0]

            status, confidence = classify(result, model.names)
            annotated = result.plot()

            # Require consecutive matching frames before
            # changing the confirmed state.
            if status == candidate:
                streak += 1
            else:
                candidate = status
                streak = 1

            if (
                candidate != "NONE"
                and streak >= CONFIRM_FRAMES
                and candidate != current_state
            ):
                current_state = candidate
                snapshot = ""

                timestamp = datetime.now().isoformat(
                    timespec="seconds"
                )

                # Save an image only for a helmet violation.
                if current_state == "VIOLATION":
                    filename = datetime.now().strftime(
                        "violation_%Y%m%d_%H%M%S_%f.jpg"
                    )

                    snapshot = os.path.join(
                        SNAPSHOT_DIR,
                        filename
                    )

                    if not cv2.imwrite(snapshot, annotated):
                        print(
                            f"\n[ERROR] Could not save {snapshot}"
                        )
                        snapshot = ""

                # Save the event in SQLite.
                save_event(
                    current_state,
                    confidence,
                    timestamp,
                    snapshot,
                )

                # Publish the same event to HiveMQ.
                publish_event(
                    client,
                    current_state,
                    confidence,
                    timestamp,
                    snapshot,
                )

            cv2.putText(
                annotated,
                f"STATE: {current_state}",
                (10, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                colors[current_state],
                3,
            )

            publish_frame(annotated)

            if SHOW_WINDOW:
                cv2.imshow(
                    "MFU Helmet Safety Entry-System",
                    annotated,
                )

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

    except KeyboardInterrupt:
        print("\n[INFO] Stopping detector...")

    finally:
        cap.release()
        cv2.destroyAllWindows()
        client.loop_stop()
        client.disconnect()

        print("[INFO] Camera and MQTT client stopped.")


if __name__ == "__main__":
    main()