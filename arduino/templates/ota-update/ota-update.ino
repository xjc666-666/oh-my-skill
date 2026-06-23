/*
 * 项目: ArduinoOTA 无线更新
 * 板子: ESP32 (ESP32系列)
 * 日期: <当前日期>
 *
 * 通过 WiFi OTA（无线）更新固件
 * 首次烧录需通过 USB 串口，后续可通过 WiFi 无线更新
 */

#include <WiFi.h>
#include <ArduinoOTA.h>

// ===== WiFi 配置 =====
const char* WIFI_SSID     = "你的WiFi名称";
const char* WIFI_PASSWORD = "你的WiFi密码";

// ===== OTA 配置 =====
const char* OTA_HOSTNAME = "esp32-ota";  // 在 Arduino IDE / arduino-cli 中显示的主机名
const char* OTA_PASSWORD = "";           // OTA 密码（留空=无密码）

// ===== LED =====
#define LED_PIN  2

void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println();
    Serial.println("===== ArduinoOTA 无线更新 =====");

    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, LOW);

    // 连接 WiFi
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.print("连接 WiFi");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println();
    Serial.print("已连接, IP: ");
    Serial.println(WiFi.localIP());

    // 配置 OTA
    ArduinoOTA.setHostname(OTA_HOSTNAME);

    if (strlen(OTA_PASSWORD) > 0) {
        ArduinoOTA.setPassword(OTA_PASSWORD);
    }

    ArduinoOTA.onStart([]() {
        String type = (ArduinoOTA.getCommand() == U_FLASH) ? "固件" : "文件系统";
        Serial.println("开始更新 " + type);
    });

    ArduinoOTA.onEnd([]() {
        Serial.println("\n更新完成");
    });

    ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
        Serial.printf("进度: %u%%\r", (progress * 100) / total);
    });

    ArduinoOTA.onError([](ota_error_t error) {
        Serial.printf("错误[%u]: ", error);
        if (error == OTA_AUTH_ERROR)      Serial.println("认证失败");
        else if (error == OTA_BEGIN_ERROR) Serial.println("开始失败");
        else if (error == OTA_CONNECT_ERROR)Serial.println("连接失败");
        else if (error == OTA_RECEIVE_ERROR)Serial.println("接收失败");
        else if (error == OTA_END_ERROR)   Serial.println("结束失败");
    });

    ArduinoOTA.begin();

    Serial.println("OTA 已就绪");
    Serial.print("主机名: ");
    Serial.println(OTA_HOSTNAME);

    // 首次上传需通过 USB，之后可通过 WiFi OTA:
    // arduino-cli upload -p <主机名>.local -b <FQBN> <sketch_path>
    if (strlen(OTA_PASSWORD) > 0) {
        Serial.println("⚠ OTA 需要密码");
    }
    Serial.println("OTA 上传命令:");
    Serial.print("  arduino-cli upload -p ");
    Serial.print(OTA_HOSTNAME);
    Serial.println(".local -b <FQBN> <sketch>");
}

void loop() {
    ArduinoOTA.handle();  // 处理 OTA 请求

    // 你的应用程序代码
    // LED 闪烁表示正常运行
    digitalWrite(LED_PIN, millis() % 2000 < 1000 ? HIGH : LOW);
}
