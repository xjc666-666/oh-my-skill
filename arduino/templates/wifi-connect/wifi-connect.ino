/*
 * 项目: WiFi 连接
 * 板子: <板名> (<FQBN>)
 * 日期: <当前日期>
 *
 * 连接到指定的 WiFi 网络，串口输出连接状态和 IP 地址
 * 断线后自动重连
 */

#include <WiFi.h>
#include "secrets.h"

// ===== WiFi 配置 =====
// WIFI_SSID 和 WIFI_PASSWORD 定义在 secrets.h 中，防止泄露

// ===== WiFi 重连配置 =====
const unsigned long WIFI_RECONNECT_INTERVAL = 30000;  // 30 秒检查一次
unsigned long lastWiFiCheck = 0;

void connectWiFi() {
    Serial.print("正在连接 WiFi: ");
    Serial.println(WIFI_SSID);

    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 20) {
        delay(500);
        Serial.print(".");
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println();
        Serial.println("WiFi 已连接");
        Serial.print("IP 地址: ");
        Serial.println(WiFi.localIP());
    } else {
        Serial.println();
        Serial.println("WiFi 连接失败");
    }
}

void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println();
    Serial.println("===== WiFi 连接演示 =====");

    // 设置 WiFi 为 STA 模式
    WiFi.mode(WIFI_STA);
    connectWiFi();
}

void loop() {
    // 定时检查 WiFi 状态，断线自动重连
    if (millis() - lastWiFiCheck > WIFI_RECONNECT_INTERVAL) {
        lastWiFiCheck = millis();
        if (WiFi.status() != WL_CONNECTED) {
            Serial.println("WiFi 已断开，尝试重连...");
            WiFi.disconnect();
            delay(1000);
            connectWiFi();
        }
    }

    // 你的主循环代码
}
