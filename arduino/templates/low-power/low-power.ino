/*
 * 项目: 低功耗演示
 * 板子: ESP32 (ESP32系列)
 * 日期: <当前日期>
 *
 * 演示 ESP32 Deep Sleep 低功耗模式
 * 定时器唤醒 + 外部按钮唤醒
 */

// ===== 引脚定义 =====
#define WAKEUP_BUTTON_PIN  GPIO_NUM_33   // 唤醒按钮（需 RTC_GPIO）
#define LED_PIN            2

// ===== 睡眠时间 =====
#define SLEEP_SECONDS  10    // 睡眠秒数

// 检查唤醒原因
void printWakeupReason() {
    esp_sleep_wakeup_cause_t wakeup_reason = esp_sleep_get_wakeup_cause();

    switch (wakeup_reason) {
        case ESP_SLEEP_WAKEUP_TIMER:
            Serial.println("唤醒原因: 定时器");
            break;
        case ESP_SLEEP_WAKEUP_EXT0:
            Serial.println("唤醒原因: 外部引脚 (EXT0)");
            break;
        case ESP_SLEEP_WAKEUP_EXT1:
            Serial.println("唤醒原因: 外部引脚 (EXT1)");
            break;
        case ESP_SLEEP_WAKEUP_TOUCHPAD:
            Serial.println("唤醒原因: 触摸引脚");
            break;
        default:
            Serial.printf("唤醒原因: 其他 (%d)\n", wakeup_reason);
            break;
    }
}

void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println();
    Serial.println("===== Deep Sleep 低功耗演示 =====");

    // 检查唤醒原因
    printWakeupReason();

    // 短暂闪烁 LED 表示唤醒
    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, HIGH);
    delay(200);
    digitalWrite(LED_PIN, LOW);

    Serial.println("正在工作...");
    Serial.println("将在 " + String(SLEEP_SECONDS) + " 秒后进入 Deep Sleep");

    // 模拟工作
    delay(2000);

    // 配置唤醒源
    Serial.println("配置唤醒源...");

    // 1. 定时器唤醒
    esp_sleep_enable_timer_wakeup(SLEEP_SECONDS * 1000000ULL);
    Serial.printf("- 定时器: %d 秒后唤醒\n", SLEEP_SECONDS);

    // 2. 外部引脚唤醒（按钮）
    esp_sleep_enable_ext0_wakeup(WAKEUP_BUTTON_PIN, LOW);
    Serial.printf("- 外部引脚: GPIO%d 低电平唤醒\n", WAKEUP_BUTTON_PIN);

    // 可选: 触摸唤醒
    // esp_sleep_enable_touchpad_wakeup();

    Serial.println("进入 Deep Sleep...");
    Serial.println("唤醒方式: 等待定时器 或 按下按钮");
    Serial.println();
    delay(100);

    // 进入 Deep Sleep
    esp_deep_sleep_start();
}

void loop() {
    // Deep Sleep 下不会运行 loop()
    // 每次唤醒都会重新执行 setup()
}
