/*
 * 项目: RGB LED PWM 调光
 * 板子: <板名> (<FQBN>)
 * 引脚: RED=<用户指定>, GREEN=<用户指定>, BLUE=<用户指定>
 * 日期: <当前日期>
 *
 * 使用 PWM 控制 RGB LED 实现渐变调光效果
 * LED 引脚需要串联 220Ω 限流电阻
 */

// ===== 引脚定义 =====
#define RED_PIN    13    // 红色通道
#define GREEN_PIN  12    // 绿色通道
#define BLUE_PIN   14    // 蓝色通道

// ===== PWM 参数 =====
#define PWM_FREQ     5000    // PWM 频率 (Hz)
#define PWM_RESOLUTION 8     // 分辨率 (8位: 0-255)

void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println();
    Serial.println("===== RGB LED PWM 调光 =====");

    // 配置 PWM 通道
    ledcAttach(RED_PIN, PWM_FREQ, PWM_RESOLUTION);
    ledcAttach(GREEN_PIN, PWM_FREQ, PWM_RESOLUTION);
    ledcAttach(BLUE_PIN, PWM_FREQ, PWM_RESOLUTION);

    Serial.println("演示: 红色渐变 → 绿色渐变 → 蓝色渐变 → 混合");
}

// 设置 RGB 颜色 (0-255)
void setColor(uint8_t r, uint8_t g, uint8_t b) {
    ledcWrite(RED_PIN, r);
    ledcWrite(GREEN_PIN, g);
    ledcWrite(BLUE_PIN, b);
}

void loop() {
    // 红色渐变 (0 → 255 → 0)
    Serial.println("红色渐变...");
    for (int i = 0; i <= 255; i++) {
        setColor(i, 0, 0);
        delay(10);
    }
    for (int i = 255; i >= 0; i--) {
        setColor(i, 0, 0);
        delay(10);
    }

    // 绿色渐变
    Serial.println("绿色渐变...");
    for (int i = 0; i <= 255; i++) {
        setColor(0, i, 0);
        delay(10);
    }
    for (int i = 255; i >= 0; i--) {
        setColor(0, i, 0);
        delay(10);
    }

    // 蓝色渐变
    Serial.println("蓝色渐变...");
    for (int i = 0; i <= 255; i++) {
        setColor(0, 0, i);
        delay(10);
    }
    for (int i = 255; i >= 0; i--) {
        setColor(0, 0, i);
        delay(10);
    }

    // 彩虹渐变
    Serial.println("彩虹渐变...");
    for (int angle = 0; angle < 360; angle++) {
        float rad = angle * PI / 180.0;
        int r = (sin(rad) * 127 + 128);
        int g = (sin(rad + 2.094) * 127 + 128);  // +120°
        int b = (sin(rad + 4.189) * 127 + 128);  // +240°
        setColor(r, g, b);
        delay(20);
    }
}
