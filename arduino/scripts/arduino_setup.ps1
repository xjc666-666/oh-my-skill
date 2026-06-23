# arduino_setup.ps1
# Arduino 开发环境检测与初始化脚本
# 用法: pwsh -File arduino_setup.ps1
#       pwsh -File arduino_setup.ps1 -InstallCli  (自动安装 arduino-cli)
# 输出: JSON 格式的环境报告

param(
    [switch]$InstallCli = $false,
    [switch]$ForceRecheck = $false
)

$ErrorActionPreference = "Stop"

# ===== 路径常量 =====
$Arduino15Path = Join-Path $env:LOCALAPPDATA "Arduino15"
$ArduinoIdePath = Join-Path $env:LOCALAPPDATA "Programs\Arduino IDE"
$CliInstallPath = Join-Path $env:LOCALAPPDATA "Arduino15\cli"
$CliExecutable = Join-Path $CliInstallPath "arduino-cli.exe"

# ===== 结果对象 =====
$Report = @{
    timestamp          = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    arduino_cli        = @{ installed = $false; version = ""; path = "" }
    arduino_ide        = @{ installed = $false; path = "" }
    arduino15          = @{ exists = $false; path = $Arduino15Path }
    platforms          = @()
    serial_drivers     = @{ ch340 = $false; cp210x = $false }
    errors             = @()
    warnings           = @()
    recommendations    = @()
}

# ===== 检测 arduino-cli =====
function Test-ArduinoCli {
    try {
        $cli = Get-Command "arduino-cli" -ErrorAction SilentlyContinue
        if ($cli) {
            $Report.arduino_cli.installed = $true
            $Report.arduino_cli.path = $cli.Source
            $version = & arduino-cli version --format json 2>$null | ConvertFrom-Json
            $Report.arduino_cli.version = $version.VersionString
            return $true
        }
    } catch {}

    if (Test-Path $CliExecutable) {
        $Report.arduino_cli.installed = $true
        $Report.arduino_cli.path = $CliExecutable
        try {
            $version = & $CliExecutable version --format json 2>$null | ConvertFrom-Json
            $Report.arduino_cli.version = $version.VersionString
        } catch {
            $Report.warnings += "arduino-cli found but cannot determine version"
        }
        return $true
    }

    return $false
}

# ===== 检测 Arduino IDE v2 =====
function Test-ArduinoIde {
    $exe = Join-Path $ArduinoIdePath "Arduino IDE.exe"
    if (Test-Path $exe) {
        $Report.arduino_ide.installed = $true
        $Report.arduino_ide.path = $ArduinoIdePath
        return $true
    }
    return $false
}

# ===== 检测 Arduino15 数据目录 =====
function Test-Arduino15 {
    if (Test-Path $Arduino15Path) {
        $Report.arduino15.exists = $true

        # 检测已安装平台
        $packagesDir = Join-Path $Arduino15Path "packages"
        if (Test-Path $packagesDir) {
            Get-ChildItem -LiteralPath $packagesDir -Directory | ForEach-Object {
                $vendor = $_.Name
                $hardwareDir = Join-Path $_.FullName "hardware"
                if (Test-Path $hardwareDir) {
                    Get-ChildItem -LiteralPath $hardwareDir -Directory | ForEach-Object {
                        $arch = $_.Name
                        Get-ChildItem -LiteralPath $_.FullName -Directory | ForEach-Object {
                            $version = $_.Name
                            $Report.platforms += "$vendor`:$arch`:$version"
                        }
                    }
                }
            }
        }
        return $true
    }
    return $false
}

# ===== 检测串口驱动 =====
function Test-SerialDrivers {
    # 检测 CH340/CH341 驱动
    $ch340 = Get-WmiObject Win32_PnPSignedDriver -Filter "DeviceName LIKE '%CH340%' OR DeviceName LIKE '%CH341%'" -ErrorAction SilentlyContinue
    if ($ch340) {
        $Report.serial_drivers.ch340 = $true
    }

    # 检测 CP210x 驱动
    $cp210x = Get-WmiObject Win32_PnPSignedDriver -Filter "DeviceName LIKE '%CP210%'" -ErrorAction SilentlyContinue
    if ($cp210x) {
        $Report.serial_drivers.cp210x = $true
    }
}

# ===== 安装 arduino-cli =====
function Install-ArduinoCli {
    Write-Host "正在安装 arduino-cli..."

    $zipUrl = "https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_Windows_64bit.zip"
    $zipPath = Join-Path $env:TEMP "arduino-cli.zip"

    try {
        # 创建安装目录
        if (-not (Test-Path $CliInstallPath)) {
            New-Item -ItemType Directory -Force -Path $CliInstallPath | Out-Null
        }

        # 下载
        Write-Host "下载: $zipUrl"
        Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -ErrorAction Stop

        # 解压
        Write-Host "解压到: $CliInstallPath"
        Expand-Archive -Path $zipPath -DestinationPath $CliInstallPath -Force

        # 添加到 PATH
        $currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")
        if ($currentPath -notlike "*$CliInstallPath*") {
            [Environment]::SetEnvironmentVariable("PATH", "$currentPath;$CliInstallPath", "User")
            $env:PATH = "$env:PATH;$CliInstallPath"
            Write-Host "已添加到用户 PATH: $CliInstallPath"
        } else {
            Write-Host "路径已在 PATH 中"
        }

        # 配置 arduino-cli
        Write-Host "配置 arduino-cli..."
        $configDir = Join-Path $env:LOCALAPPDATA "Arduino15"
        & $CliExecutable config init
        & $CliExecutable config set directories.data $configDir --config-file (Join-Path $configDir "arduino-cli.yaml")

        # 更新平台索引
        Write-Host "更新平台索引..."
        & $CliExecutable core update-index

        # 设置全局可执行（无需写完整路径）
        $env:PATH = "$env:PATH;$CliInstallPath"

        Remove-Item $zipPath -ErrorAction SilentlyContinue
        Write-Host "arduino-cli 安装完成"
        return $true
    } catch {
        $Report.errors += "安装 arduino-cli 失败: $_"
        Write-Host "安装失败: $_"
        return $false
    }
}

# ===== 主流程 =====
Write-Host "===== Arduino 环境检测 =====" -ForegroundColor Cyan
Write-Host ""

# 1. 检测 arduino-cli
Write-Host "[1/4] 检测 arduino-cli..." -ForegroundColor Yellow
if (Test-ArduinoCli) {
    Write-Host "  $([char]0x2714) arduino-cli $($Report.arduino_cli.version)" -ForegroundColor Green
    Write-Host "     路径: $($Report.arduino_cli.path)"
} else {
    Write-Host "  $([char]0x2716) arduino-cli 未安装" -ForegroundColor Red
    $Report.warnings += "arduino-cli 未安装"

    if ($InstallCli) {
        Write-Host "  正在安装 arduino-cli..."
        if (Install-ArduinoCli) {
            Test-ArduinoCli
        }
    } else {
        $Report.recommendations += "运行此脚本带 -InstallCli 参数自动安装: pwsh -File arduino_setup.ps1 -InstallCli"
    }
}
Write-Host ""

# 2. 检测 Arduino IDE
Write-Host "[2/4] 检测 Arduino IDE..." -ForegroundColor Yellow
if (Test-ArduinoIde) {
    Write-Host "  $([char]0x2714) Arduino IDE 已安装" -ForegroundColor Green
    Write-Host "     路径: $ArduinoIdePath"
} else {
    Write-Host "  - Arduino IDE 未安装（非必需，arduino-cli 可独立工作）" -ForegroundColor DarkGray
}
Write-Host ""

# 3. 检测 Arduino15 数据目录
Write-Host "[3/4] 检测 Arduino15 数据目录..." -ForegroundColor Yellow
if (Test-Arduino15) {
    Write-Host "  $([char]0x2714) Arduino15 数据目录存在" -ForegroundColor Green
    Write-Host "     路径: $Arduino15Path"
    if ($Report.platforms.Count -gt 0) {
        Write-Host "     已安装平台:"
        $Report.platforms | ForEach-Object { Write-Host "       - $_" }
    } else {
        Write-Host "     警告: 未安装任何平台包" -ForegroundColor Yellow
        $Report.warnings += "未安装任何平台包，需执行 arduino-cli core install"
    }
} else {
    Write-Host "  $([char]0x2716) Arduino15 数据目录不存在" -ForegroundColor Red
    $Report.errors += "Arduino15 目录不存在，arduino-cli 将无法工作"
}
Write-Host ""

# 4. 检测串口驱动
Write-Host "[4/4] 检测串口驱动..." -ForegroundColor Yellow
Test-SerialDrivers
if ($Report.serial_drivers.ch340) {
    Write-Host "  $([char]0x2714) CH340/CH341 驱动" -ForegroundColor Green
} else {
    Write-Host "  - CH340/CH341 驱动未检测到" -ForegroundColor DarkGray
    $Report.recommendations += "如果使用 CH340 芯片的开发板，请安装 CH340 驱动"
}
if ($Report.serial_drivers.cp210x) {
    Write-Host "  $([char]0x2714) CP210x 驱动" -ForegroundColor Green
} else {
    Write-Host "  - CP210x 驱动未检测到" -ForegroundColor DarkGray
    $Report.recommendations += "如果使用 CP210x 芯片的开发板，请安装 CP210x 驱动"
}
Write-Host ""

# ===== 输出 JSON 报告 =====
Write-Host "===== 环境报告 (JSON) =====" -ForegroundColor Cyan
$Report | ConvertTo-Json -Depth 4

# ===== 总结 =====
Write-Host ""
Write-Host "===== 检测总结 =====" -ForegroundColor Cyan

$statusOk = $true

if (-not $Report.arduino_cli.installed) {
    Write-Host "  $([char]0x2716) arduino-cli 未安装 - 需要安装" -ForegroundColor Red
    $statusOk = $false
}
if (-not $Report.arduino15.exists) {
    Write-Host "  $([char]0x2716) Arduino15 目录不存在" -ForegroundColor Red
    $statusOk = $false
}
if ($Report.platforms.Count -eq 0) {
    Write-Host "  $([char]0x26A0) 无已安装平台 - 需至少安装一个平台" -ForegroundColor Yellow
}

if ($Report.errors.Count -gt 0) {
    Write-Host ""
    Write-Host "错误:" -ForegroundColor Red
    $Report.errors | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
}

if ($Report.warnings.Count -gt 0) {
    Write-Host ""
    Write-Host "警告:" -ForegroundColor Yellow
    $Report.warnings | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
}

if ($Report.recommendations.Count -gt 0) {
    Write-Host ""
    Write-Host "建议:" -ForegroundColor Cyan
    $Report.recommendations | ForEach-Object { Write-Host "  - $_" -ForegroundColor White }
}

if ($statusOk) {
    Write-Host ""
    Write-Host "$([char]0x2714) Arduino 开发环境就绪" -ForegroundColor Green
}

exit ($statusOk ? 0 : 1)
