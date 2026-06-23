#!/usr/bin/env bash
# arduino_setup.sh
# Arduino 开发环境检测与初始化脚本 (macOS / Linux)
# 用法: bash arduino_setup.sh
#       bash arduino_setup.sh --install-cli  (自动安装 arduino-cli)
# 输出: JSON 格式的环境报告

set -euo pipefail

INSTALL_CLI=false
if [[ "${1:-}" == "--install-cli" ]]; then
    INSTALL_CLI=true
fi

# ===== 平台检测 =====
detect_os() {
    case "$(uname -s)" in
        Darwin*)  echo "macos" ;;
        Linux*)   echo "linux" ;;
        *)        echo "unknown" ;;
    esac
}

OS=$(detect_os)

# ===== 路径常量 =====
if [[ "$OS" == "macos" ]]; then
    ARDUINO15_PATH="$HOME/Library/Arduino15"
    ARDUINO_IDE_PATH="/Applications/Arduino IDE.app"
    CLI_INSTALL_PATH="$HOME/bin"
    CLI_EXECUTABLE="$CLI_INSTALL_PATH/arduino-cli"
elif [[ "$OS" == "linux" ]]; then
    ARDUINO15_PATH="$HOME/.arduino15"
    ARDUINO_IDE_PATH="$HOME/.arduinoide"
    CLI_INSTALL_PATH="$HOME/.local/bin"
    CLI_EXECUTABLE="$CLI_INSTALL_PATH/arduino-cli"
else
    echo "{\"error\": \"Unsupported OS: $OS\"}"
    exit 1
fi

# ===== JSON 构建辅助 =====
JSON_OUTPUT="{}"

# ===== 检测 arduino-cli =====
detect_cli() {
    local cli_path
    cli_path=$(which arduino-cli 2>/dev/null || true)
    
    if [[ -n "$cli_path" ]]; then
        JSON_OUTPUT=$(echo "$JSON_OUTPUT" | jq --arg v "$(arduino-cli version --format json 2>/dev/null || echo '{}')" --arg p "$cli_path" '. + {arduino_cli: {installed: true, version: ($v | fromjson).VersionString // "", path: $p}}')
        return 0
    fi

    if [[ -x "$CLI_EXECUTABLE" ]]; then
        JSON_OUTPUT=$(echo "$JSON_OUTPUT" | jq --arg v "$("$CLI_EXECUTABLE" version --format json 2>/dev/null || echo '{}')" --arg p "$CLI_EXECUTABLE" '. + {arduino_cli: {installed: true, version: ($v | fromjson).VersionString // "", path: $p}}')
        return 0
    fi

    JSON_OUTPUT=$(echo "$JSON_OUTPUT" | jq '. + {arduino_cli: {installed: false, version: "", path: ""}}')
    return 1
}

# ===== 安装 arduino-cli =====
install_cli() {
    echo "正在安装 arduino-cli..." >&2

    mkdir -p "$CLI_INSTALL_PATH"

    if [[ "$OS" == "macos" ]]; then
        # macOS: 使用 Homebrew 或官方安装脚本
        if command -v brew &>/dev/null; then
            brew install arduino-cli 2>/dev/null && {
                echo "已通过 Homebrew 安装 arduino-cli" >&2
                return 0
            }
        fi
    fi

    # 通用安装脚本（Linux + macOS 备用）
    local install_url="https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh"
    curl -fsSL "$install_url" | BINDIR="$CLI_INSTALL_PATH" sh

    # 确保在 PATH 中
    if [[ ":$PATH:" != *":$CLI_INSTALL_PATH:"* ]]; then
        echo "export PATH=\"$CLI_INSTALL_PATH:\$PATH\"" >> "$HOME/.bashrc"
        [[ -f "$HOME/.zshrc" ]] && echo "export PATH=\"$CLI_INSTALL_PATH:\$PATH\"" >> "$HOME/.zshrc"
        export PATH="$CLI_INSTALL_PATH:$PATH"
    fi

    echo "arduino-cli 安装完成" >&2
    return 0
}

# ===== 检测 Arduino15 =====
detect_arduino15() {
    if [[ -d "$ARDUINO15_PATH" ]]; then
        local platforms="[]"
        local packages_dir="$ARDUINO15_PATH/packages"
        
        if [[ -d "$packages_dir" ]]; then
            for vendor in "$packages_dir"/*/; do
                [[ -d "$vendor" ]] || continue
                local vendor_name=$(basename "$vendor")
                local hardware_dir="${vendor}hardware"
                
                if [[ -d "$hardware_dir" ]]; then
                    for arch in "$hardware_dir"/*/; do
                        [[ -d "$arch" ]] || continue
                        local arch_name=$(basename "$arch")
                        for ver in "$arch"/*/; do
                            [[ -d "$ver" ]] || continue
                            local ver_name=$(basename "$ver")
                            platforms=$(echo "$platforms" | jq --arg p "${vendor_name}:${arch_name}:${ver_name}" '. + [$p]')
                        done
                    done
                fi
            done
        fi

        JSON_OUTPUT=$(echo "$JSON_OUTPUT" | jq --arg path "$ARDUINO15_PATH" --argjson plats "$platforms" '. + {arduino15: {exists: true, path: $path, platforms: $plats}}')
        return 0
    else
        JSON_OUTPUT=$(echo "$JSON_OUTPUT" | jq --arg path "$ARDUINO15_PATH" '. + {arduino15: {exists: false, path: $path, platforms: []}}')
        return 1
    fi
}

# ===== 检测 Arduino IDE =====
detect_ide() {
    local found=false
    local ide_path=""

    if [[ "$OS" == "macos" ]] && [[ -d "$ARDUINO_IDE_PATH" ]]; then
        found=true
        ide_path="$ARDUINO_IDE_PATH"
    elif [[ "$OS" == "linux" ]] && [[ -d "$ARDUINO_IDE_PATH" ]]; then
        found=true
        ide_path="$ARDUINO_IDE_PATH"
    fi

    # 也检查 PATH 中是否有 arduino 命令
    if [[ "$found" == "false" ]]; then
        local arduino_cmd
        arduino_cmd=$(which arduino 2>/dev/null || true)
        if [[ -n "$arduino_cmd" ]]; then
            found=true
            ide_path=$(dirname "$arduino_cmd")
        fi
    fi

    JSON_OUTPUT=$(echo "$JSON_OUTPUT" | jq --argjson installed "$found" --arg path "$ide_path" '. + {arduino_ide: {installed: $installed, path: $path}}')
}

# ===== 检测串口权限 =====
detect_serial_perms() {
    local has_perms=false
    local tty_devices=""
    
    if [[ "$OS" == "linux" ]]; then
        if groups | grep -qE '\b(dialout|uucp)\b'; then
            has_perms=true
        fi
        tty_devices=$(ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | tr '\n' ' ' || echo "")
    elif [[ "$OS" == "macos" ]]; then
        tty_devices=$(ls /dev/cu.usb* /dev/tty.usb* 2>/dev/null | tr '\n' ' ' || echo "")
        # macOS 通常默认有权限
        has_perms=true
    fi

    JSON_OUTPUT=$(echo "$JSON_OUTPUT" | jq --argjson perms "$has_perms" --arg devices "$tty_devices" '. + {serial: {has_permissions: $perms, devices: ($devices | split(" ") | map(select(length > 0)))}}')
}

# ===== 主流程 =====
echo "===== Arduino 环境检测 =====" >&2
echo "平台: $OS" >&2
echo "" >&2

# 1. 检测 arduino-cli
echo "[1/4] 检测 arduino-cli..." >&2
if detect_cli; then
    echo "  ✔ arduino-cli 已安装" >&2
else
    echo "  ✘ arduino-cli 未安装" >&2
    if $INSTALL_CLI; then
        echo "  正在安装..." >&2
        if install_cli; then
            detect_cli
        else
            echo "  安装失败" >&2
        fi
    else
        echo "  提示: 使用 --install-cli 参数自动安装" >&2
    fi
fi
echo "" >&2

# 2. 检测 Arduino IDE
echo "[2/4] 检测 Arduino IDE..." >&2
detect_ide
if echo "$JSON_OUTPUT" | jq -e '.arduino_ide.installed' >/dev/null 2>&1; then
    echo "  ✔ Arduino IDE 已安装" >&2
else
    echo "  - Arduino IDE 未安装（非必需）" >&2
fi
echo "" >&2

# 3. 检测 Arduino15
echo "[3/4] 检测 Arduino15..." >&2
if detect_arduino15; then
    echo "  ✔ Arduino15 目录存在" >&2
    local count=$(echo "$JSON_OUTPUT" | jq '.arduino15.platforms | length' 2>/dev/null || echo "0")
    if [[ "$count" -gt 0 ]]; then
        echo "  已安装平台:" >&2
        echo "$JSON_OUTPUT" | jq -r '.arduino15.platforms[] | "    - \(.)"' 2>/dev/null >&2
    else
        echo "  警告: 未安装任何平台包" >&2
    fi
else
    echo "  ✘ Arduino15 目录不存在" >&2
fi
echo "" >&2

# 4. 检测串口权限
echo "[4/4] 检测串口权限..." >&2
detect_serial_perms

if [[ "$OS" == "linux" ]]; then
    if echo "$JSON_OUTPUT" | jq -e '.serial.has_permissions' >/dev/null 2>&1; then
        echo "  ✔ 串口权限正常 (dialout/uucp 组)" >&2
    else
        echo "  ✘ 缺少串口权限，执行: sudo usermod -a -G dialout \$USER" >&2
    fi
else
    echo "  - macOS: 默认有串口权限" >&2
fi

# 显示检测到的设备
local devices=$(echo "$JSON_OUTPUT" | jq -r '.serial.devices[]?' 2>/dev/null || echo "")
if [[ -n "$devices" ]]; then
    echo "  可用串口设备:" >&2
    echo "$devices" | while read -r dev; do
        echo "    - $dev" >&2
    done
fi

echo "" >&2

# ===== 输出 JSON 报告 =====
echo "===== 环境报告 (JSON) =====" >&2

# 添加时间戳
final_output=$(echo "$JSON_OUTPUT" | jq --arg ts "$(date -u +"%Y-%m-%d %H:%M:%S")" '. + {timestamp: $ts}')

echo "$final_output" | jq '.'

# ===== 检测总结 =====
echo "" >&2
echo "===== 检测总结 =====" >&2

has_cli=$(echo "$final_output" | jq '.arduino_cli.installed')
has_arduino15=$(echo "$final_output" | jq '.arduino15.exists')

status_ok=true

if [[ "$has_cli" != "true" ]]; then
    echo "  ✘ arduino-cli 未安装 - 需要安装" >&2
    status_ok=false
fi

if [[ "$has_arduino15" != "true" ]]; then
    echo "  ✘ Arduino15 目录不存在" >&2
    status_ok=false
fi

if $status_ok; then
    echo "  ✔ Arduino 开发环境就绪" >&2
    exit 0
else
    exit 1
fi
