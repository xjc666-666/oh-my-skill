/*
 * 项目: MQTT 客户端（WiFi + MQTT）
 * 板子: <板名> (<FQBN>)
 * 日期: <当前日期>
 *
 * 连接到 WiFi 和 MQTT 服务器
 * 定时发布消息，接收订阅主题的消息
 */

#include <WiFi.h>
#include <PubSubClient.h>

// ===== WiFi 配置 =====
const char* WIFI_SSID     = "你的WiFi名称";
const char* WIFI_PASSWORD = "你的WiFi密码";

// ===== MQTT 配置 =====
const char* MQTT_SERVER   = "broker.emqx.io";  // 免费公共 MQTT 服务器
const int   MQTT_PORT     = 1883;
const char* MQTT_CLIENT_ID = "ESP32_Client";
const char* MQTT_TOPIC_PUB = "arduino/test";    // 发布主题
const char* MQTT_TOPIC_SUB = "arduino/cmd";     // 订阅主题

// ===== 上报间隔 =====
const unsigned long REPORT_INTERVAL = 10000;  // 10 秒上报一次
unsigned long lastReportTime = 0;

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

// MQTT 收到消息的回调函数
void mqttCallback(char* topic, byte* payload, unsigned int length) {
    Serial.print("收到消息 [");
    Serial.print(topic);
    Serial.print("]: ");

    for (unsigned int i = 0; i < length; i++) {
        Serial.print((char)payload[i]);
    }
    Serial.println();
}

void connectWiFi() {
    Serial.print("连接 WiFi: ");
    Serial.println(WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println();
    Serial.print("已连接, IP: ");
    Serial.println(WiFi.localIP());
}

void connectMQTT() {
    Serial.print("连接 MQTT 服务器: ");
    Serial.println(MQTT_SERVER);
    while (!mqttClient.connected()) {
        if (mqttClient.connect(MQTT_CLIENT_ID)) {
            Serial.println("MQTT 连接成功");
            mqttClient.subscribe(MQTT_TOPIC_SUB);
            Serial.print("已订阅: ");
            Serial.println(MQTT_TOPIC_SUB);
        } else {
            Serial.print("MQTT 连接失败, rc=");
            Serial.print(mqttClient.state());
            Serial.println(" 5秒后重试");
            delay(5000);
        }
    }
}

void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println();
    Serial.println("===== MQTT 客户端 =====");

    WiFi.mode(WIFI_STA);
    connectWiFi();

    mqttClient.setServer(MQTT_SERVER, MQTT_PORT);
    mqttClient.setCallback(mqttCallback);
    connectMQTT();
}

void loop() {
    // 确保 MQTT 连接正常
    if (!mqttClient.connected()) {
        connectMQTT();
    }
    mqttClient.loop();

    // 定时上报
    if (millis() - lastReportTime > REPORT_INTERVAL) {
        lastReportTime = millis();

        char msg[64];
        snprintf(msg, sizeof(msg), "uptime: %lu ms", millis());
        mqttClient.publish(MQTT_TOPIC_PUB, msg);
        Serial.print("已发布: ");
        Serial.println(msg);
    }
}
