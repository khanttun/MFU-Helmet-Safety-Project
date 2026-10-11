/*
  MFU Helmet Safety Entry-System - ESP32 barrier controller
  Subscribes to  <PREFIX>/cmd     ("OPEN" | "CLOSE")
  Publishes to   <PREFIX>/status  ("OPEN" | "CLOSED" | "OFFLINE")  (retained)

  Libraries (Library Manager): PubSubClient (Nick O'Leary), ESP32Servo (Kevin Harrington)
  Wiring: Servo signal -> GPIO 18, Servo VCC -> 5V (VIN), Servo GND -> GND (common with ESP32)
*/
#include <cstring>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ESP32Servo.h>

// ---------- EDIT THESE ----------
const char* WIFI_SSID = "kent";
const char* WIFI_PASS = "12345678";

const char* MQTT_HOST = "broker.hivemq.com";   // or xxxx.s1.eu.hivemq.cloud
const int   MQTT_PORT = 1883;                  // 8883 for HiveMQ Cloud
const bool  USE_TLS   = false;                 // true for HiveMQ Cloud
const char* MQTT_USER = "";                    // HiveMQ Cloud credentials
const char* MQTT_PASS = "";

const char* TOPIC_PREFIX = "mfu-helmet-6731502018";  // must match Python + Node-RED
// --------------------------------

const int SERVO_PIN    = 18;
const int OPEN_ANGLE   = 90;   // barrier raised
const int CLOSED_ANGLE = 0;    // barrier lowered

String topicCmd, topicStatus;
WiFiClient plainClient;
WiFiClientSecure secureClient;
PubSubClient mqtt;
Servo barrier;
bool isClosed = false;

void publishStatus() {
  mqtt.publish(topicStatus.c_str(), isClosed ? "CLOSED" : "OPEN", true);
}

void setBarrier(bool close) {
  isClosed = close;
  barrier.write(close ? CLOSED_ANGLE : OPEN_ANGLE);
  Serial.println(close ? "Barrier CLOSED" : "Barrier OPEN");
  publishStatus();
}

void onMessage(char* topic, byte* payload, unsigned int len) {
  String msg;
  for (unsigned int i = 0; i < len; i++) msg += (char)payload[i];
  msg.trim();
  msg.toUpperCase();
  Serial.printf("MQTT [%s]: %s\n", topic, msg.c_str());
  if (msg == "CLOSE") setBarrier(true);
  else if (msg == "OPEN") setBarrier(false);
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println("\nWiFi OK, IP: " + WiFi.localIP().toString());
}

void connectMQTT() {
  while (!mqtt.connected()) {
    String clientId = "esp32-barrier-" + String((uint32_t)ESP.getEfuseMac(), HEX);
    Serial.print("Connecting MQTT...");
    bool ok = mqtt.connect(clientId.c_str(),
                           strlen(MQTT_USER) ? MQTT_USER : nullptr,
                           strlen(MQTT_USER) ? MQTT_PASS : nullptr,
                           topicStatus.c_str(), 1, true, "OFFLINE");
    if (ok) {
      Serial.println("connected");
      mqtt.subscribe(topicCmd.c_str(), 1);
      publishStatus();
    } else {
      Serial.printf("failed rc=%d, retry in 3s\n", mqtt.state());
      delay(3000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  topicCmd    = String(TOPIC_PREFIX) + "/cmd";
  topicStatus = String(TOPIC_PREFIX) + "/status";

  barrier.setPeriodHertz(50);
  barrier.attach(SERVO_PIN, 500, 2400);
  setBarrier(false);  // default: permitted-entry (open) state

  connectWiFi();
  if (USE_TLS) {
    secureClient.setInsecure();  // demo only; load the broker CA certificate for production
    mqtt.setClient(secureClient);
  } else {
    mqtt.setClient(plainClient);
  }
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMessage);
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();
  if (!mqtt.connected()) connectMQTT();
  mqtt.loop();
}
