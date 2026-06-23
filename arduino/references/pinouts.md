# 引脚映射与分配指南

## 引脚信息来源

### 方式1：硬编码速查（主流板，精确）

以下常用板的引脚映射已硬编码，无需文件解析。

### 方式2：动态解析（全部已安装板）

```bash
# 找到板子对应的 pins_arduino.h 路径
# FQBN: 例如 "esp32:esp32:esp32"

# 解析 variants 目录
# 路径模式（各平台用 / 分隔替代 \）:
#   Arduino15/packages/<vendor>/hardware/<arch>/<version>/variants/<board>/pins_arduino.h

# 用 grep 提取引脚定义
grep -E "#define\s+(PIN_|D\d+|A\d+|SDA|SCL|MOSI|MISO|SCK|SS|LED_BUILTIN)" \
  <Arduino15路径>/packages/<vendor>/hardware/<arch>/<version>/variants/<board>/pins_arduino.h
```

## Arduino Uno R3 引脚速查

| Arduino 编号 | ATmega328P 端口 | 功能 | 备注 |
|-------------|-----------------|------|------|
| D0 | PD0 | RX | 串口接收 |
| D1 | PD1 | TX | 串口发送 |
| D2 | PD2 | INT0 | 外部中断 0 |
| D3 | PD3 | INT1 / PWM | 外部中断 1 |
| D4 | PD4 | GPIO | |
| D5 | PD5 | PWM | |
| D6 | PD6 | PWM | |
| D7 | PD7 | GPIO | |
| D8 | PB0 | GPIO | |
| D9 | PB1 | PWM | |
| D10 | PB2 | SS / PWM | SPI 片选 |
| D11 | PB3 | MOSI / PWM | SPI |
| D12 | PB4 | MISO | SPI |
| D13 | PB5 | SCK / LED_BUILTIN | SPI 时钟 |
| A0 | PC0 | ADC0 | 模拟输入 0 |
| A1 | PC1 | ADC1 | 模拟输入 1 |
| A2 | PC2 | ADC2 | 模拟输入 2 |
| A3 | PC3 | ADC3 | 模拟输入 3 |
| A4 | PC4 | SDA / ADC4 | I2C 数据 |
| A5 | PC5 | SCL / ADC5 | I2C 时钟 |

## Arduino Nano 引脚速查

| 编号 | 功能 | 编号 | 功能 |
|------|------|------|------|
| D0 | RX | D7 | GPIO |
| D1 | TX | D8 | GPIO |
| D2 | INT0 | D9 | PWM |
| D3 | INT1 / PWM | D10 | SS / PWM |
| D4 | GPIO | D11 | MOSI / PWM |
| D5 | PWM | D12 | MISO |
| D6 | PWM | D13 | SCK / LED_BUILTIN |
| A0-A3 | ADC | A4-A5 | ADC / SDA-SCL |
| A6-A7 | ADC(仅输入) | | |

## Arduino Mega 2560 引脚速查

**特殊外设引脚：**

| 外设 | 引脚 |
|------|------|
| I2C (Wire) | SDA=20, SCL=21 |
| SPI | MISO=50, MOSI=51, SCK=52, SS=53 |
| Serial1 | RX=19, TX=18 |
| Serial2 | RX=17, TX=16 |
| Serial3 | RX=15, TX=14 |
| LED_BUILTIN | 13 |

PWM 引脚：2-13, 44-46

## ESP32 Dev Module (38-pin) 引脚速查

```
┌────────────────────────────────────┐
│  ESP32 DevKit V1 / NodeMCU-32S    │
│                                    │
│  ADC:  ADC1: 32-39                │
│         ADC2: 0,2,4,12-15,25-27   │
│                                    │
│  I2C 默认: SDA=21, SCL=22         │
│  SPI 默认 (VSPI):                 │
│    MISO=19, MOSI=23, SCK=18, SS=5 │
│  SPI 第二组 (HSPI):               │
│    MISO=12, MOSI=13, SCK=14, SS=15│
│                                    │
│  Serial0 (默认): RX=3, TX=1       │
│  Serial1: RX=9, TX=10             │
│  Serial2: RX=16, TX=17            │
│                                    │
│  LED_BUILTIN: 2 (大多数板)        │
│  Strapping: 0,2,4,5,12,15        │
│  仅输入:  34,35,36,39             │
│  内置上拉: 所有输出引脚            │
│                                    │
│  常用免费 GPIO:                    │
│    输出: 13,18,19,21,22,23,25,26, │
│           27,32,33                 │
│    输入: 34,35,36,39 (仅输入)      │
└────────────────────────────────────┘
```

## ESP32-S3 Dev Module 引脚速查

| 功能 | 引脚 |
|------|------|
| I2C 默认 | SDA=8, SCL=9 (或 SDA=41, SCL=42) |
| SPI 默认 (SPI2/FSPI) | MISO=13, MOSI=11, SCK=12, SS=10 |
| SPI 第二组 (SPI3) | MISO=37, MOSI=35, SCK=36, SS=34 |
| UART0 (USB-Serial-JTAG) | RX=44, TX=43 |
| UART1 | RX=18, TX=17 |
| LED_BUILTIN | 48 (大部分板) |
| 内置 USB JTAG | USB 直连调试 |
| Strapping | 0,3,45,46 |
| 仅输入 | 46 |
| PSRAM 占用 (8线) | 6-11, 16-17 |
| JTAG 默认 | 12-15 |

## ESP32-C3 Dev Module 引脚速查

| 功能 | 引脚 |
|------|------|
| I2C 默认 | SDA=5, SCL=6 (或 SDA=8, SCL=10) |
| SPI 默认 | MISO=7, MOSI=6, SCK=5, SS=4 |
| UART0 (USB-Serial-JTAG) | RX=20, TX=21 |
| LED_BUILTIN | 8 (大部分板) |
| 内置 USB JTAG | USB 直连调试 |
| Strapping | 2,8,9 |

## 引脚自动分配算法

```
输入: 外设需求列表 [{类型: "I2C", 用途: "OLED"},
                    {类型: "SPI", 用途: "SD卡"},
                    {类型: "GPIO", 方向: "OUTPUT", 用途: "LED"},
                    {类型: "GPIO", 方向: "INPUT_PULLUP", 用途: "按钮"}]

步骤:
1. 从板子引脚表加载所有可用引脚及其功能

2. 标记不可用引脚:
   - Strapping 引脚
   - 仅输入引脚（对外设需要 OUTPUT 的）
   - PSRAM 占用引脚（如果启用 PSRAM）
   - 已分配给其他外设的引脚

3. 按优先级分配:
   a) I2C: 优先默认 SDA/SCL，否则任意两个空闲引脚
   b) SPI: 优先默认 MISO/MOSI/SCK，CS 任选空闲引脚
   c) UART: 优先默认 TX/RX
   d) ADC: 优先 ADC1 (ESP32)，避免 ADC2 (WiFi冲突)
   e) PWM: 选择支持 PWM 的引脚
   f) 普通 GPIO: 从剩余空闲引脚中选择

4. 冲突检测:
   - 同一引脚被分配两次 → 错误
   - Strapping 引脚被普通 GPIO 使用 → 警告 + 替代建议
   - ADC2 在 WiFi 模式下使用 → 警告
   - 输入引脚无上拉/下拉 → 建议添加

5. 输出引脚分配表
```

## 引脚约束规则库

### 通用约束（所有板子）
- 输入引脚建议配置上拉/下拉，避免悬空
- 中断引脚数量有限，优先使用外部中断引脚
- PWM 引脚数量有限，参考板子 datasheet

### AVR 特定约束
- Uno 的 D0/D1 是串口，烧录时不要用作其他用途
- Nano 的 A6/A7 仅模拟输入

### ESP32 特定约束
- 见 `references/esp32-config.md` 引脚约束章节
