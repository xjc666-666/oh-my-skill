/*
 * 项目: Web 服务器
 * 板子: <板名> (<FQBN>)
 * 日期: <当前日期>
 *
 * 启动一个简单的 HTTP Web 服务器
 * 访问根路径返回 HTML 页面，访问 /api/data 返回 JSON
 */

#include <WiFi.h>
#include <WebServer.h>

// ===== WiFi 配置 =====
const char* WIFI_SSID     = "你的WiFi名称";
const char* WIFI_PASSWORD = "你的WiFi密码";

// ===== Web 服务器 =====
WebServer server(80);  // HTTP 默认端口 80

void handleRoot() {
    String html = R"rawliteral(
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ESP32 Web 服务器</title>
    <style>
        body { font-family: sans-serif; text-align: center; margin-top: 50px; }
        .status { color: green; font-weight: bold; }
    </style>
</head>
<body>
    <h1>ESP32 Web 服务器</h1>
    <p class="status">运行中</p>
    <p>运行时间: )rawliteral";
    html += String(millis() / 1000);
    html += " 秒</p>";
    html += "<p><a href='/api/data'>查看 API 数据</a></p>";
    html += "</body></html>";

    server.send(200, "text/html; charset=utf-8", html);
}

void handleAPI() {
    String json = "{";
    json += "\"uptime\":" + String(millis()) + ",";
    json += "\"freeHeap\":" + String(ESP.getFreeHeap()) + ",";
    json += "\"wifiRSSI\":" + String(WiFi.RSSI());
    json += "}";

    server.send(200, "application/json", json);
}

void handleNotFound() {
    server.send(404, "text/plain", "404 - 页面未找到");
}

void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println();
    Serial.println("===== Web 服务器 =====");

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

    // 注册路由
    server.on("/", handleRoot);
    server.on("/api/data", handleAPI);
    server.onNotFound(handleNotFound);

    // 启动服务器
    server.begin();
    Serial.println("HTTP 服务器已启动");
    Serial.print("在浏览器中打开: http://");
    Serial.println(WiFi.localIP());
}

void loop() {
    server.handleClient();  // 处理 HTTP 请求
}
