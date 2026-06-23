/*
 * 项目: DHT 温湿度传感器
 * 板子: <板名> (<FQBN>)
 * 引脚: DHT_DATA = <用户指定>
 * 日期: <当前日期>
 *
 * 读取 DHT11 / DHT22 温湿度传感器数据，通过串口输出
 */

#include <DHT.h>

// ===== 引脚定义 =====
#define DHT_PIN    4       // DHT 数据引脚（GPIO4）
#define DHT_TYPE    DHT11   // DHT11 或 DHT22

DHT dht(DHT_PIN, DHT_TYPE);

void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println();
    Serial.println("===== DHT 温湿度传感器 =====");

    dht.begin();
    Serial.print("传感器类型: ");
    Serial.println(DHT_TYPE == DHT11 ? "DHT11" : "DHT22");
}

void loop() {
    delay(2000);  // DHT 传感器读取间隔至少 2 秒

    float humidity = dht.readHumidity();
    float temperature = dht.readTemperature();
    // 华氏度: float f = dht.readTemperature(true);

    if (isnan(humidity) || isnan(temperature)) {
        Serial.println("读取传感器失败!");
        return;
    }

    // 计算体感温度（简化公式）
    float heatIndex = dht.computeHeatIndex(temperature, humidity, false);

    Serial.println("========== 环境数据 ==========");
    Serial.printf("  温度:     %.1f °C\n", temperature);
    Serial.printf("  湿度:     %.1f %%\n", humidity);
    Serial.printf("  体感温度: %.1f °C\n", heatIndex);
    Serial.println("==============================");
}
