# Oh My Skill

欢迎来到 **Oh My Skill**。这是一个专为 Claude（或兼容的 LLM Agent）设计的定制化、高度自动化的工作流 Skill 集合，旨在大幅加速嵌入式系统和固件开发。

## 📦 仓库结构

本仓库包含以下功能模块，它们分别存放在对应的文件夹中：

### 1. [arduino](./arduino)
一个端到端的 Arduino 框架开发 Skill。它在后台调用 `arduino-cli`，可全自动完成项目骨架创建、库依赖管理、代码编译、错误智能修复以及固件烧录。支持 AVR（如 Uno/Nano）、ESP32、RISC-V 等主流平台。
👉 [详细介绍及使用方法](./arduino/README.md)

### 2. [stm32-keil](./stm32-keil)
全面覆盖 STM32 开发的 Keil MDK-ARM 自动化工作流。支持标准外设库（SPL）和 HAL 库，能够解析 CubeMX 的 `.ioc` 文件，集成了强大的编译错误恢复机制、CMSIS-DAP 自动烧录以及 HardFault 源码定位与分析。
👉 [详细介绍及使用方法](./stm32-keil/README.md)

### 3. [mspm0g3519](./mspm0g3519)
专为德州仪器 Cortex-M0+ 架构的 MSPM0G3519 芯片量身定制的固件开发 Skill。它深度融合了 TI SysConfig 和 Keil 工具链，强制执行严格的引脚分配校验，并能处理特定的硬件校准（如 VREF 实测值），通过三级代码质量检查机制保障代码的健壮性。
👉 [详细介绍及使用方法](./mspm0g3519/README.md)

## 🚀 如何使用

1. 克隆或下载本仓库中你需要的 Skill 文件夹。
2. 将对应的文件夹部署到你的 Claude Desktop、Claude Dev (Roo Code) 或任何支持 `.claude/skills` 结构的 Agent 环境目录中。
3. 在对话中，直接用自然语言向 Agent 下达硬件开发、代码生成、排错或烧录指令即可。

## ⚠️ 全局注意事项

- **硬件引脚校验 (Hardware Validation)**：在涉及实际的硬件连线时，Agent 可能会自动分配默认的管脚。**请务必在生成代码和烧录前仔细核对这些引脚**，避免短路或损坏设备。
- **本地工具链 (Toolchain Availability)**：这些 Skill 的自动化过程强依赖于你本地主机的命令行工具（例如 `arduino-cli`, Keil UV4 命令行, Python 脚本等）。请确保你的系统中已经正确安装了对应的环境，且配置在了系统的环境变量 `PATH` 中。
