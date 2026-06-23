/*
 * 项目: HC-SR04 超声波测距
 * 板子: <板名> (<FQBN>)
 * 引脚: TRIG=<用户指定>, ECHO=<用户指定>
 * 日期: <当前日期>
 *
 * 使用 HC-SR04 超声波传感器测量距离
 */

// ===== 引脚定义 =====
#define TRIG_PIN  5     // 触发引脚
#define ECHO_PIN   18    // 回响引脚

// ===== 参数 =====
#define MAX_DISTANCE 400  // 最大测量距离（cm）
#define TIMEOUT_US  (MAX_DISTANCE * 58)  // 超时时间（微秒）

void setup() {
    Serial.begin(115200);
    delay(1000);

    pinMode(TRIG_PIN, OUTPUT);
    pinMode(ECHO_PIN, INPUT);

    Serial.println();
    Serial.println("===== HC-SR04 超声波测距 =====");
}

float measureDistance() {
    // 发送 10μs 脉冲
    digitalWrite(TRIG_PIN, LOW);
    delayMicroseconds(2);
    digitalWrite(TRIG_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(TRIG_PIN, LOW);

    // 读取回响时间
    long duration = pulseIn(ECHO_PIN, HIGH, TIMEOUT_US);

    if (duration == 0) {
        return -1;  // 超时，无回响
    }

    // 距离 = 时间 × 声速 / 2
    // 声速 ≈ 340m/s = 0.034 cm/μs
    return duration * 0.034 / 2;
}

void loop() {
    float distance = measureDistance();

    if (distance < 0) {
        Serial.println("测距失败（超出范围或传感器未连接）");
    } else {
        Serial.printf("距离: %.1f cm\n", distance);
    }

    delay(500);  // 每秒测 2 次
}
