# SysConfig Rules

Use this file before editing `User/config.syscfg`, generating `ti_msp_dl_config.*`, or debugging pin/clock/peripheral generation issues.

## Inspect Before Edit

```bash
python {skill_dir}/scripts/syscfg_parser.py \
  --syscfg {project}/User/config.syscfg --list-modules
python {skill_dir}/scripts/syscfg_parser.py \
  --syscfg {project}/User/config.syscfg --list-pins
python {skill_dir}/scripts/syscfg_parser.py \
  --syscfg {project}/User/config.syscfg --list-clock
```

## Edit Through the Parser

Prefer `syscfg_parser.py` for add, remove, clock, and conflict work:

```bash
python {skill_dir}/scripts/syscfg_parser.py \
  --syscfg {project}/User/config.syscfg \
  --add-peripheral '{"module":"/ti/driverlib/UART","instance":"UART_1","name":"UART_0","baud":115200,"peripheral":"UART0","tx":"PA10","rx":"PA11"}'
```

Always run:

```bash
python {skill_dir}/scripts/syscfg_parser.py \
  --syscfg {project}/User/config.syscfg --check-conflicts
```

## Property Order Is Critical

SysConfig can silently ignore pin assignment when properties appear in the wrong order.

GPIO pin order:

```js
GPIO2.associatedPins[0].$name            = "H1";
GPIO2.associatedPins[0].direction        = "INPUT";
GPIO2.associatedPins[0].internalResistor = "PULL_UP";
GPIO2.associatedPins[0].pin.$assign      = "PB6";
```

Peripheral instance order:

```js
SPI1.$name              = "SPI_0";
SPI1.peripheral.$assign = "SPI0";
SPI1.targetBitRate      = 20000000;
SPI1.frameFormat        = "MOTO3";
```

`$name` and `peripheral.$assign` must appear before dependent settings. `pin.$assign` should appear after pin naming and direction settings.

## Generate and Verify

Generate code after SysConfig edits:

```bash
python {skill_dir}/scripts/syscfg_generator.py \
  --project-dir {project} --sdk-path {sdk_path}
```

Then verify generated output instead of assuming the `.syscfg` edit worked:

- `User/ti_msp_dl_config.h` contains the expected port/pin macros.
- `User/ti_msp_dl_config.c` initializes the expected modules.
- Fixed OLED and Keyboard pins still match `references/hardware_pin_map.json`.
- Newly added peripherals do not reuse fixed pins.

Useful checks:

```bash
rg "PORT|PIN|IRQN|INST" {project}/User/ti_msp_dl_config.h
rg "DL_.*init|DL_.*enable" {project}/User/ti_msp_dl_config.c
```

## Generated File Rule

Treat `ti_msp_dl_config.c` and `ti_msp_dl_config.h` as generated files. Fix durable configuration in `config.syscfg`, then regenerate. Manual edits to generated files are only acceptable for short diagnostics and must be called out.

## Pin Config $name Must Be Unique

When multiple peripherals have pin config properties (`xxxPinConfig.$name`), each must use a **unique** name. SysConfig treats duplicate names as errors and silently drops the conflicting peripheral.

**错误示例**（SPI MOSI 和 DAC 输出都用 Generic1）：
```js
SPI1.mosiPinConfig.$name  = "ti_driverlib_gpio_GPIOPinGeneric1";  // SPI 占了 Generic1
DAC12.OutPinConfig.$name  = "ti_driverlib_gpio_GPIOPinGeneric1";  // 冲突！DAC 被丢弃
```

**正确示例**（每个外设用不同的 Generic 编号）：
```js
SPI1.sclkPinConfig.$name  = "ti_driverlib_gpio_GPIOPinGeneric0";  // SCLK
SPI1.mosiPinConfig.$name  = "ti_driverlib_gpio_GPIOPinGeneric1";  // MOSI
DAC12.OutPinConfig.$name  = "ti_driverlib_gpio_GPIOPinGeneric2";  // DAC 输出
```

**验证方法**：生成 syscfg 后检查 stderr 是否有 `Duplicate name` 错误，以及 `ti_msp_dl_config.h` 中是否包含所有预期的外设宏定义。

## 硬件排查优先

当 OLED/外设不工作时，**先用参考工程验证硬件**，再怀疑代码。步骤：
1. 编译烧录参考工程（`references/EVM_TEST_OLED/` 或用户已知可用的工程）
2. 如果参考工程也不工作 → 硬件问题（屏幕坏、接线松、供电不足）
3. 如果参考工程工作 → 对比 syscfg 和代码差异
