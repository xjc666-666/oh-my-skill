/*
 * 项目: LED 闪烁
 * 板子: <板名> (<FQBN>)
 * 引脚: LED_BUILTIN
 * 日期: <当前日期>
 *
 * 基础模板 - 验证板子和开发环境是否正常工作
 */

// 大多数板子内置 LED 连接到引脚 LED_BUILTIN
// 如果板子无内置 LED，改用其他引脚并外接 LED+220Ω电阻

void setup() {
    pinMode(LED_BUILTIN, OUTPUT);
}

void loop() {
    digitalWrite(LED_BUILTIN, HIGH);  // 点亮
    delay(1000);                       // 等待 1 秒
    digitalWrite(LED_BUILTIN, LOW);   // 熄灭
    delay(1000);                       // 等待 1 秒
}
