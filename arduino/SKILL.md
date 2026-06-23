---
name: arduino
description: Use when working with Arduino microcontrollers -- creating projects, writing code, compiling, uploading, serial monitoring, debugging. Covers AVR (Uno/Nano/Mega), ESP32 series, SG200X RISC-V, and any Arduino-supported platform. Use when user mentions Arduino, .ino, ESP32, sketch, arduino-cli, board flashing, or microcontroller development targeting Arduino framework.
---

# Arduino 全流程开发 Skill

## 概述与核心定位

一句话需求到烧录验证的全自动化 Arduino 开发流程。基于 `arduino-cli` 命令行工具，复用 Arduino15 数据目录中已安装的工具链和平台包，支持 AVR / ESP32 / SG200X 等所有已安装平台。

**作为 AI Agent，你的核心职责是：**
1. **优先使用专用工具**：使用 `run_command` 执行 CLI 命令，使用 `write_to_file` 或 `replace_file_content` 编写代码和配置文件。
2. **适配系统环境**：当前主机环境为主流操作系统（主要为 Windows，使用 PowerShell）。如果是 Windows，执行命令时切勿直接复制 Bash 语法（如 `export`、`grep`），需转换为对应的 PowerShell 命令（如 `$env:`、`Select-String`）或直接执行 `arduino-cli` 跨平台语法。
3. **闭环操作机制**：执行操作后，**必须检查**命令的输出结果（如编译错误、端口占用），并自动进行最多 3 次尝试修复，不要每次遇到小错误都停下来问用户。
4. **管理长时间运行的任务**：例如串口监控 (`monitor`) 会阻塞进程，请通过 `WaitMsBeforeAsync` 参数将其放入后台，使用 `manage_task` 定期检查其状态和输出，或在验证完毕后直接 `kill` 任务。

## 何时使用本 Skill

**触发场景：**
- 用户提到 Arduino / .ino / sketch / 开发板相关关键词
- 用户说"写个ESP32程序"、"编译"、"烧录"、"上传"、"选板子"等
- 需要从零创建嵌入式项目（温湿度监控、WiFi连接、MQTT、传感器驱动等）
- 编译报错需要诊断修复、烧录失败需要排查
- 涉及引脚分配、硬件配置（Flash模式、分区表、CPU频率等）

**不使用场景：**
- 纯软件项目（与硬件无关）
- 非 Arduino 框架的嵌入式开发（裸机 C、PlatformIO、STM32CubeIDE 等 —— 除非用户明确要求不用 PlatformIO）
- Arduino 理论学习（非实操）

---

## 阶段 0：环境检测与初始化

首次使用或用户要求检查环境时，根据操作系统使用 `run_command` 执行对应脚本：

| 平台 | 脚本 | 建议执行命令 (在 run_command 中) |
|------|------|------|
| Windows | `scripts/arduino_setup.ps1` | `pwsh -File scripts\arduino_setup.ps1 -InstallCli` |
| macOS/Linux | `scripts/arduino_setup.sh` | `bash scripts/arduino_setup.sh --install-cli` |

脚本执行后，会自动检测或安装 `arduino-cli`，并输出环境报告。如果无脚本，请手动执行：
```powershell
arduino-cli version
arduino-cli board list
```
未安装时，请提示用户或通过命令自动下载 `arduino-cli` 至 PATH。

---

## 阶段 1：核心工作流（全自动流水线）

针对自然语言需求，请自动跑通以下全流程：

### 步骤 1：需求解析与板子选型
1. **提取需求**：确定芯片类型、外设列表、功能目标、特殊需求（如低功耗、OTA、SPIFFS文件系统）。
2. **确定 FQBN（Fully Qualified Board Name）**：
   - 查阅 `references/boards-quickref.md` 匹配常用板。
   - 或执行 `arduino-cli board listall | Select-String -Pattern "关键词"` 查找。
3. **平台依赖检查**：FQBN 对应的核心包若未安装，执行 `arduino-cli core install <vendor>:<arch>`。

### 步骤 2：引脚分配与冲突检查
查阅 `references/pinouts.md`，或解析 `variants/<board>/pins_arduino.h`。
**ESP32 系列致命约束检查：**
- **Strapping 引脚** (GPIO0,2,4,5,12,15)：严禁用于影响启动电平的外设，若必须使用需明确警告。
- **ADC2 冲突**：开启 WiFi 时 ADC2 (GPIO4,0,2,12-15,25-27,32-39) 不可用。
- **仅输入引脚**：ESP32(GPIO34-39), ESP32-S3(GPIO46) 无内部上下拉，且不能配置为 OUTPUT。
- **冲突检测**：同一引脚不得被两个外设复用。

### 步骤 3：工程结构与代码生成
- **工作区隔离**：为每个新工程在根目录自动创建 `arduino-cli.yaml`，并配置 `directories.user: .`，确保第三方库存放在本工程的 `libraries/` 下，实现依赖隔离。
- **工程结构**：
  - 小于等于 2 个外设：单文件 `.ino`。
  - 多于 3 个外设：自动拆分为 `<name>.ino` + `config.h` + `<module>.cpp`。
- **凭证分离与安全**：涉及 WiFi 密码、MQTT Token 等敏感信息时，**必须**创建 `secrets.h` 并在 `.gitignore` 中将其忽略。主程序仅通过 `#include "secrets.h"` 引用。
- **前后端分离 (Web UI)**：若需求包含 Web 页面展示或交互，**禁止在 C++ 中使用长 String 拼接 HTML**。必须在工程目录下创建 `data/` 文件夹，将 `index.html`、`style.css` 存入其中，并通过 LittleFS/SPIFFS 进行读取响应。
- **代码规范**：顶部添加注释块（项目名、板名、引脚、日期），采用英文变量名+中文注释，确保 `Serial.begin` 波特率设置一致。

### 步骤 4：库依赖解析与安装
扫描代码中所有的 `#include <...>`，过滤内置库（`Arduino.h`, `WiFi.h`, `Wire.h`, `SPI.h`, `FS.h`, `LittleFS.h`, `EEPROM.h` 等）。
使用 `arduino-cli lib install "库名"` 自动安装缺失的第三方库（例如 `PubSubClient`, `ArduinoJson`）。注意：`<DHT.h>` 对应 `DHT sensor library`。

### 步骤 5：板级配置与编译 (Compile)
执行 `arduino-cli board details -b <FQBN>` 获取配置。
- **ESP32 常用覆盖项**：若有 OTA 或代码大于 1MB，加 `--build-properties "PartitionScheme=huge_app"`；低功耗需求加 `"CPUFrequencyMHz=80"`。
执行编译（**强制开启严格警告**）：
```powershell
arduino-cli compile -b <FQBN> --warnings all --build-properties "<配置项列表>" <Sketch路径>
```
如果在编译时发现 Warning（特别是内存和指针相关的警告），请主动分析并修正 C++ 隐患。
**如有 SPIFFS/LittleFS**：需要在编译后处理文件系统镜像构建。

### 步骤 6：烧录与上传 (Upload)
执行 `arduino-cli board list` 匹配串口 (`COMx` 或 `/dev/ttyUSBx`)。
执行烧录：
```powershell
arduino-cli upload -p <PORT> -b <FQBN> <Sketch路径>
```
- **SPIFFS 上传**：`arduino-cli upload -p <PORT> --upload-field target=filesystem -b <FQBN> <Sketch路径>`
- **OTA 上传**：识别代码中有 ArduinoOTA 时，端口改为设备 IP：`arduino-cli upload -p <IP> -b <FQBN> <Sketch路径>`

### 步骤 7：串口监控与验证 (Monitor)
烧录成功后，开启监控以验证期望输出：
```powershell
# 作为后台任务运行，配置 WaitMsBeforeAsync > 0
arduino-cli monitor -p <PORT> -c baudrate=<波特率>
```
根据代码特征设定超时预期：
- `Serial.println`：预期有数据输出（超时 10s）。
- `WiFi.begin`：预期 "Connected"（超时 15s）。
验证完毕后，立刻使用 `manage_task` 终止进程。

---

## 阶段 2：自动化错误恢复 (Troubleshooting)

最多尝试 3 次自动修复。若失败，再向用户输出诊断报告。

### 编译错误修复：
- `'xxx' was not declared`：补充缺失的库 `#include` 或全局变量。
- `fatal error: xxx.h`：执行 `arduino-cli lib install` 补充安装。
- `no matching function`：调用库 API 出错，查阅头文件更正。

### 烧录错误修复：
- **"access denied" / "port busy"**：提示用户关闭 IDE 串口或其他占用程序。
- **"chip not in download mode" / "Invalid head" (ESP32)**：提示用户按住板子的 BOOT 按钮并重试。
- **Upload speed error**：在编译参数中降速（`--build-properties "UploadSpeed=115200"`）。
- **"avrdude: stk500_getsync()"** (AVR)：检查引脚占用或重试一次。

### 运行时奔溃破译 (Exception Decoding)：
当串口监视器中出现类似 `Backtrace: 0x40083412:0x3ffb1230...` 的奔溃乱码时，请执行以下命令进行自动化破译，定位空指针或溢出发生的具体代码行：
```powershell
# 请根据实际安装路径寻找 xtensa-esp32-elf-addr2line 工具
<toolchain_path>/xtensa-esp32-elf-addr2line -pfiaC -e <build_path>/<project>.elf <崩溃地址>
```

---

## 阶段 3：硬件调试支持 (Debugging)
当用户要求 `debug` 且板子支持 JTAG（如 ESP32-S3 内置 USB JTAG）时：
1. 配置 `--build-properties "JTAGAdapter=builtin"` 并加上调试符号 `-g` 重新编译。
2. 启动 OpenOCD 和 GDB，根据 `references/` 文档指导用户进行 `target remote`。
3. 不支持 JTAG 的板子：通过插入 `Serial.print` 追踪或根据 Exception Backtrace 诊断。

## 附录：核心参考资源
- `references/boards-quickref.md` —— 板子速查与 FQBN
- `references/esp32-config.md` —— ESP32 详细配置
- `references/sg200x-config.md` —— SG200X RISC-V 板级配置
- `references/pinouts.md` —— 芯片级与板级引脚约束
- `scripts/arduino_setup.ps1` —— Windows 环境初始化脚本
- `templates/` —— 官方与用户沉淀的代码模板
