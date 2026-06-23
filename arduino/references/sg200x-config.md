# SG200X (DuoS) 配置

## 概述

SG200X 是 SOPHGO 的 RISC-V 双核处理器（1GHz C906 + 700MHz C906 + 8051 MCU）。Arduino 支持通过 `sophgo:SG200X` 平台包。

## 板子列表

| 板子 | FQBN | 主要参数 |
|------|------|----------|
| DuoS | `sophgo:SG200X:duos` | 256MB DDR3, USB-C, Ethernet |

## 配置项

执行获取：
```bash
arduino-cli board details -b sophgo:SG200X:duos
```

### 典型配置

| 配置项 | 可选值 | 默认 | 说明 |
|--------|--------|------|------|
| UploadSpeed | 115200 / 921600 / 1500000 | 1500000 | 串口烧录速度 |
| CPUFrequencyMHz | 1000 | 1000 | C906 大核频率 |
| FlashMode | qio / dio | dio | Flash 通信模式 |
| FlashSize | - | 板默认 | |

## 烧录工具链

SG200X 使用 `burntool_py` 进行烧录，位于：
```
Arduino15/packages/sophgo/tools/burntool_py/<version>/
```

烧录命令（arduino-cli 自动处理）：
```bash
arduino-cli upload -p <PORT> -b sophgo:SG200X:duos <sketch_path>
```

## 引脚约束

SG200X 的引脚映射解析路径：
```
Arduino15/packages/sophgo/hardware/SG200X/<version>/variants/<board>/pins_arduino.h
```

### 特殊注意事项

1. **启动模式**：部分引脚在启动时决定启动源（SD卡 / Flash / USB），用作 GPIO 前需确认
2. **电压电平**：多数 GPIO 为 3.3V（非 5V 耐受），连接 5V 外设需电平转换
3. **Linux + Arduino 双系统**：Arduino 固件运行在 RISC-V 小核上，大核运行 Linux
4. **烧录模式**：需要进入烧录模式（按住 BOOT 按钮再上电或按 RESET）

## 编译工具链

使用 `xpack-riscv-none-elf-gcc`，位于：
```
Arduino15/packages/sophgo/tools/xpack-riscv-none-elf-gcc/<version>/
```
