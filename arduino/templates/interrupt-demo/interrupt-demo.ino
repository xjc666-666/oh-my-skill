/*
 * 项目: 外部中断演示
 * 板子: <板名> (<FQBN>)
 * 引脚: BUTTON_PIN = <用户指定>
 * 日期: <当前日期>
 *
 * 演示外部中断和软件防抖
 * 按钮按下触发中断，防抖后切换 LED 状态
 */

// ===== 引脚定义 =====
#define BUTTON_PIN  0     // 按钮（使用 INPUT_PULLUP）
#define LED_PIN     2     // LED

// ===== 防抖参数 =====
#define DEBOUNCE_DELAY 50   // 防抖延迟（毫秒）

volatile bool buttonPressed = false;       // 中断标志
volatile unsigned long lastInterrupt = 0;  // 上次中断时间

// 中断服务函数
void IRAM_ATTR handleButtonInterrupt() {
    unsigned long now = millis();
    // 简单的防抖：忽略间隔太短的中断
    if (now - lastInterrupt > DEBOUNCE_DELAY) {
        buttonPressed = true;
        lastInterrupt = now;
    }
}

void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println();
    Serial.println("===== 外部中断演示 =====");

    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, LOW);

    pinMode(BUTTON_PIN, INPUT_PULLUP);

    // 绑定中断：下降沿触发（按钮按下 GND）
    attachInterrupt(digitalPinToInterrupt(BUTTON_PIN),
                    handleButtonInterrupt, FALLING);

    Serial.println("按按钮切换 LED 状态");
    Serial.println("中断引脚: " + String(BUTTON_PIN));
}

void loop() {
    if (buttonPressed) {
        buttonPressed = false;

        // 翻转 LED 状态
        static bool ledState = false;
        ledState = !ledState;
        digitalWrite(LED_PIN, ledState);

        Serial.printf("按钮按下（软件防抖后）, LED: %s\n",
                      ledState ? "开" : "关");
    }

    // 主循环可以做其他事情
    // 不需要轮询按钮，中断会自动响应
}
