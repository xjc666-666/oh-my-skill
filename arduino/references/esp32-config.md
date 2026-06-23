# ESP32 全配置详解

## 概述

ESP32 系列通过 `arduino-cli` 编译时可通过 `--build-properties` 覆盖以下配置项。各配置项的可用值因芯片型号不同而异。

获取某板的完整可用配置：
```bash
arduino-cli board details -b esp32:esp32:<chip>
```

## 配置项速查

### FlashMode

| 值 | 速度 | 稳定性 | 适用场景 |
|----|------|--------|----------|
| `qio` (默认) | 最快 | 一般 | 大多数板子 |
| `qout` | 快 | 好 | 部分板子 QIO 不稳定时 |
| `dio` | 中等 | 好 | 兼容性最好 |
| `dout` | 最慢 | 最好 | 某些板子必须用（如 ESP32-CAM） |

### FlashSize

| 值 | 实际容量 | 常见板子 |
|----|----------|----------|
| `4M` (默认) | 4MB | ESP32-DevKitC, NodeMCU-32S |
| `8M` | 8MB | ESP32-WROVER, FREENOVE |
| `16M` | 16MB | ESP32-WROVER-E, ESP32-S3-DevKitC |
| `32M` | 32MB | 部分定制板 |

### PartitionScheme (分区方案)

| 方案 | APP 分区大小 | SPIFFS | OTA | 适用场景 |
|------|-------------|--------|-----|----------|
| `default` | 1.3MB×2 | 无 | 无 | 普通项目 |
| `min_spiffs` (默认含FS) | 1.3MB×1 | 1.3MB | 无 | 需要文件系统 |
| `huge_app` | 3MB×1 | 无 | 无 | 大固件（无OTA） |
| `minimal` | 1.8MB×1 | 无 | 无 | 最小分区 |
| `no_ota` | 3.3MB×1 | 无 | 无 | 最大APP(无OTA/FS) |
| `default_ffat` | 1.3MB×2 | FFAT | 有 | FFAT替代SPIFFS |
| `min_spiffs_16M` | 3MB×1 | 6.6MB | 无 | 16MB Flash + 大文件系统 |
| `rainmaker` | ESP RainMaker 专用分区 | | ESP RainMaker |

**智能选择规则：**
- 代码含 `SPIFFS` → `min_spiffs`
- 代码含 `LittleFS` → `default` (LittleFS 不需要特殊分区)
- 代码含 `ArduinoOTA` → `min_spiffs` (含 OTA 分区)
- 代码含 `FFat` → `default_ffat`
- 无特殊需求 → `default`
- 用户强制指定 → 用指定值

### UploadSpeed

| 值 | 说明 |
|----|------|
| `921600` (默认) | 高速下载，大部分板上稳定 |
| `460800` | 中速，第一级降速 |
| `115200` | 低速，最稳定 |
| `256000` | 中速 |
| `512000` | 中高速 |

### CPUFrequencyMHz

| 值 | 功耗 | 性能 | 适用场景 |
|----|------|------|----------|
| `240` (默认) | 高 | 最高 | 正常使用 |
| `160` | 中 | 中等 | 电池供电 |
| `80` | 低 | 低 | 深度低功耗 |
| `40` | 最低 | 最低 | 超低功耗（仅部分芯片） |

### PSRAM

| 值 | 说明 |
|----|------|
| `disabled` (默认) | 不使用 PSRAM |
| `enabled` | 启用 PSRAM（需板子搭载 PSRAM） |

启用 PSRAM 时 GPIO16/17 可能被占用（部分板）。

### JTAGAdapter

| 值 | 说明 |
|----|------|
| `disabled` (默认) | 不启用 JTAG |
| `builtin` | 内置 USB JTAG (ESP32-S3/C3/C6 支持) |
| `external` | 外部 JTAG 适配器 (需飞线) |

### EraseFlash

| 值 | 说明 |
|----|------|
| `none` (默认) | 只擦除需要写的扇区 |
| `all` | 全片擦除（解决分区表兼容问题） |
| `sketch` | 只擦除 APP 分区（OTA 更新推荐） |

### LoopCore / EventsCore

控制 FreeRTOS 任务亲和性，值 `0` 或 `1`。默认均为 `1`。

## 安全特性配置

### Secure Boot (安全启动)

该功能需要 `esptool.py` (位于 `Arduino15/packages/esp32/tools/esptool_py/`)。

```bash
# 1. 生成签名密钥
espsecure.py generate_signing_key secure_boot_signing_key.pem

# 2. 烧录密钥到 eFuse（不可逆！）
espefuse.py --port <PORT> burn_key secure_boot_v2 secure_boot_signing_key.pem

# 3. 启用安全启动熔丝
espefuse.py --port <PORT> burn_efuse FLASH_CRYPT_CNT
# 再次烧录使 FLASH_CRYPT_CNT 为奇数 → 启用加密

# 4. 签名固件
espsecure.py sign_data --version 2 --keyfile secure_boot_signing_key.pem build/<firmware>.bin

# 5. 烧录签名固件
esptool.py --port <PORT> write_flash 0x0 build/<firmware_signed>.bin
```

⚠️ **安全启动是不可逆操作！** 执行前：
- 必须用户明确确认
- 备份签名密钥 (`.pem`) 到安全位置
- 密钥丢失 = 无法更新固件
- `.pem` 文件加到 `.gitignore`

### Flash Encryption (Flash 加密)

**开发模式（可重新烧录）：**
```bash
espefuse.py --port <PORT> burn_efuse FLASH_CRYPT_CNT
```

**发布模式（不可回退）：**
```bash
espefuse.py --port <PORT> burn_efuse FLASH_CRYPT_CNT
espefuse.py --port <PORT> burn_efuse DISABLE_DL_ENCRYPT
espefuse.py --port <PORT> burn_efuse DISABLE_DL_DECRYPT
espefuse.py --port <PORT> burn_efuse DISABLE_DL_CACHE
```

## 低功耗配置

### Deep Sleep 唤醒源

```cpp
// 定时器唤醒
esp_sleep_enable_timer_wakeup(10 * 1000000); // 10秒
esp_deep_sleep_start();

// 外部唤醒 (ESP32: 仅 RTC_GPIO 引脚)
esp_sleep_enable_ext0_wakeup(GPIO_NUM_33, 1);
esp_deep_sleep_start();

// Touch 引脚唤醒
esp_sleep_enable_touchpad_wakeup();
esp_deep_sleep_start();
```

### Light Sleep

```cpp
esp_sleep_enable_timer_wakeup(5 * 1000000);
esp_light_sleep_start();
```

## ESP32 变体差异速查

| 特性 | ESP32 | ESP32-S2 | ESP32-S3 | ESP32-C3 | ESP32-C6 |
|------|-------|----------|----------|----------|----------|
| CPU 架构 | Xtensa LX6 | Xtensa LX7 | Xtensa LX7 | RISC-V | RISC-V |
| 核心数 | 2 | 1 | 2 | 1 | 1 |
| WiFi | 802.11 b/g/n | 802.11 b/g/n | 802.11 b/g/n | 802.11ax(WiFi6) | 802.11ax(WiFi6) |
| 蓝牙 | BLE 4.2 | 无 | BLE 5.0 | BLE 5.0 | BLE 5.3 |
| USB | 无原生 | USB-OTG | USB-OTG | USB-Serial-JTAG | USB-Serial-JTAG |
| SRAM | 520KB | 320KB | 512KB | 400KB | 512KB |
| PSRAM | 外挂 | 外挂 | 外挂/内嵌 | 外挂 | 外挂 |
| 最高频率 | 240MHz | 240MHz | 240MHz | 160MHz | 160MHz |
| ADC2+WiFi 限制 | 有 | 有 | 无 | 无 | 无 |
| JTAG | 外部 | 外部 | 内置 USB | 内置 USB | 内置 USB |

## ESP32 引脚约束（全系列通用注意事项）

### Strapping 引脚
GPIO0, GPIO2, GPIO4, GPIO5, GPIO12, GPIO15 在启动时采样，决定启动模式。用作普通 GPIO 时需注意外接电路不要拉低/拉高。

### 仅输入引脚
- **ESP32**: GPIO34, GPIO35, GPIO36, GPIO39
- **ESP32-S2/S3**: GPIO46 (部分)
- 这些引脚无内部上拉/下拉

### ADC2 限制
ESP32 和 ESP32-S2 的 ADC2 在 WiFi 开启时不可用。使用 ADC 时优先选 ADC1 通道。

### PSRAM 引脚冲突
8线 PSRAM 占用: GPIO6-11, GPIO16-17 (ESP32-S3)
4线 PSRAM 占用: GPIO16-17 (ESP32)
启用 PSRAM 时这些引脚不可用作 GPIO。
