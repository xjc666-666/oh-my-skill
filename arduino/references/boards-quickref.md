# Arduino 板子速查表

## 快速入口（10 个最常用板）

用户输入以下关键词任一匹配即命中：

| 入口词 | 板名 | FQBN | 核心参数 |
|--------|------|------|----------|
| `uno` | Arduino Uno R3 | `arduino:avr:uno` | ATmega328P, 16MHz, 32KB Flash, 2KB SRAM, 14数字IO/6模拟 |
| `nano` | Arduino Nano | `arduino:avr:nano` | ATmega328P, 16MHz, 32KB Flash, 迷你封装, mini-USB |
| `nano-old` | Arduino Nano (ATmega168) | `arduino:avr:nano:cpu=atmega168` | ATmega168, 16KB Flash |
| `mega` | Arduino Mega 2560 | `arduino:avr:mega:cpu=atmega2560` | ATmega2560, 256KB Flash, 8KB SRAM, 54数字IO/16模拟 |
| `esp32` | ESP32 Dev Module | `esp32:esp32:esp32` | Xtensa LX6 双核, 240MHz, WiFi/BLE4.2, 520KB SRAM |
| `esp32s3` | ESP32-S3 Dev Module | `esp32:esp32:esp32s3` | Xtensa LX7 双核, WiFi/BLE5, USB-OTG, 支持PSRAM |
| `esp32c3` | ESP32-C3 Dev Module | `esp32:esp32:esp32c3` | RISC-V 单核, 160MHz, WiFi6/BLE5, 400KB SRAM |
| `esp32s2` | ESP32-S2 Dev Module | `esp32:esp32:esp32s2` | Xtensa LX7 单核, 无BLE, USB-OTG, 320KB SRAM |
| `esp32c6` | ESP32-C6 Dev Module | `esp32:esp32:esp32c6` | RISC-V, WiFi6/BLE5/Zigbee/Thread, 512KB SRAM |
| `esp8266` | NodeMCU / Wemos D1 | `esp8266:esp8266:nodemcuv2` | Xtensa L106单核, 80MHz, WiFi, 超高性价比物联网板 |
| `pico` | Raspberry Pi Pico | `rp2040:rp2040:rpipico` | RP2040 双核 ARM Cortex-M0+, 133MHz, 264KB SRAM |
| `duos` | DuoS (SG2000) | `sophgo:SG200X:duos` | RISC-V, 1GHz, 256MB DDR3, 支持 Linux+Arduino 双系统 |

## FQBN 命名规则

```
<vendor>:<architecture>:<board>[:<config_options>]

例：
  arduino:avr:uno                         # Arduino Uno
  arduino:avr:nano:cpu=atmega328old       # Nano with old bootloader
  esp32:esp32:esp32:FlashMode=dout        # ESP32 with FlashMode override
  esp32:esp32:esp32s3:PSRAM=enabled       # ESP32-S3 with PSRAM
  sophgo:SG200X:duos                      # DuoS SG2000
```

## 全量板子搜索

```bash
# 搜索所有已安装平台中匹配的板子
arduino-cli board listall | grep -i "<关键词>"

# 查看特定板子详情（含可用配置项）
arduino-cli board details -b <FQBN>

# 列出已安装的平台
arduino-cli core list
```

## 安装新平台

```bash
# 更新平台索引
arduino-cli core update-index

# 安装常用平台
arduino-cli core install arduino:avr           # AVR 板子
arduino-cli core install arduino:samd          # SAMD (Arduino Zero, MKR系列)
arduino-cli core install arduino:megaavr       # MegaAVR (Nano Every, Uno WiFi R2)
arduino-cli core install arduino:mbed_nano     # Nano 33 BLE / RP2040 Connect
arduino-cli core install arduino:renesas_uno   # Uno R4
arduino-cli core install esp32:esp32           # ESP32 全系列 (Espressif官方)
arduino-cli core install esp8266:esp8266       # ESP8266 全系列
arduino-cli core install rp2040:rp2040         # 树莓派 Pico 及 RP2040 系列 (Earle F. Philhower 维护)

# 第三方平台需要先添加 URL
arduino-cli config add board_manager.additional_urls <URL>
```

## 板子搜索关键词映射

| 用户说 | 搜索/匹配目标 |
|--------|--------------|
| uno / årdé uno | `arduino:avr:uno` |
| nano / nåno | `arduino:avr:nano` |
| 迷你 / mini | `arduino:avr:mini` |
| mega / 2560 | `arduino:avr:mega` |
| 32u4 / leonardo | `arduino:avr:leonardo` |
| 微型 / micro | `arduino:avr:micro` |
| esp32 | `esp32:esp32:esp32` |
| s3 / esp32-s3 | `esp32:esp32:esp32s3` |
| c3 / esp32-c3 | `esp32:esp32:esp32c3` |
| s2 / esp32-s2 | `esp32:esp32:esp32s2` |
| c6 / esp32-c6 | `esp32:esp32:esp32c6` |
| mkr | `arduino:samd:mkr*` |
| zero / 零 | `arduino:samd:arduino_zero_native` |
| 33ble / nano33 | `arduino:mbed_nano:nano33ble` |
| rp2040 | `arduino:mbed_nano:nanorp2040connect` |
| pico / 树莓派pico / rpipico | `rp2040:rp2040:rpipico` |
| esp8266 / nodemcu / wemos / 8266 | `esp8266:esp8266:nodemcuv2` |
| 奶昔 / duos | `sophgo:SG200X:duos` |
