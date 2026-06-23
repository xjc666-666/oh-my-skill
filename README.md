# Oh My Skill

Welcome to **Oh My Skill**, a collection of custom, highly-automated workflow Skills designed for Claude (or compatible LLM Agents) to drastically speed up embedded systems and firmware development.

## 📦 Repository Structure

This repository contains the following skills, neatly categorized into their respective folders:

### 1. [arduino](./arduino)
An end-to-end Arduino framework development skill. It uses `arduino-cli` behind the scenes to automate project creation, library management, compilation, automatic error-fixing, and firmware flashing. Supported across AVR, ESP32, RISC-V, and more.
👉 [详细介绍及使用方法](./arduino/README.md)

### 2. [stm32-keil](./stm32-keil)
A comprehensive workflow for STM32 development using Keil MDK-ARM. It supports SPL and HAL, can parse CubeMX `.ioc` files, and includes an intelligent build-error recovery loop, CMSIS-DAP flashing, and HardFault analysis.
👉 [详细介绍及使用方法](./stm32-keil/README.md)

### 3. [mspm0g3519](./mspm0g3519)
A specialized firmware development skill for TI's Cortex-M0+ MSPM0G3519 MCU. It tightly integrates TI SysConfig and Keil, enforces strict pinout checking, handles hardware-specific anomalies (like VREF calibration), and guarantees robust code through a three-tier quality check pipeline.
👉 [详细介绍及使用方法](./mspm0g3519/README.md)

## 🚀 How to Use

1. 克隆或下载本仓库中你需要的 Skill 文件夹。
2. 将文件夹部署到你的 Claude Desktop、Claude Dev (Roo Code) 或任何支持 `.claude/skills` 目录结构的 Agent 环境中。
3. 通过自然语言直接向你的 Agent 下达硬件开发、编译、烧录或 Debug 的指令。

## ⚠️ Global Precautions (全局注意事项)
- **硬件引脚校验 (Hardware Validation)**: 在涉及真实硬件连线时，Agent 生成的代码可能包含默认的引脚分配。**请务必在生成和烧录前仔细核对代码中的引脚配置**，以免造成短路或外设损坏。
- **本地工具链 (Toolchain Availability)**: 这些 Skill 大多依赖本地主机的命令行工具（如 `arduino-cli`, Keil UV4, Python 脚本等）。请确保你的系统中已经安装了对应环境，并且 Agent 具有执行这些命令的权限。
