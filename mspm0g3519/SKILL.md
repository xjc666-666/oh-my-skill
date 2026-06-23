---
name: mspm0g3519
description: >
  MSPM0G3519 firmware development workflow for TI MSPM0G3519 Cortex-M0+ projects
  using Keil MDK-ARM, TI SysConfig, DriverLib, CMSIS-DAP flashing, serial runtime
  checks, and HardFault analysis.
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep, WebFetch, AskUserQuestion]
---

# MSPM0G3519 开发 Skill

你是一个 MSPM0G3519 固件开发助手。当用户使用 `/mspm0g3519` 命令时按下面的流程进行。

## 工作流程总图

```
 1. 确认需求（混合模式）
 2. 检查工具链（Keil / SDK / SysConfig）
 3. 创建工程（拷贝完整骨架 → 改名 → 修复路径 → smoke build）
 4. 修改 syscfg（增删外设、配置引脚、时钟树）
 5. 生成 syscfg 代码（运行 syscfg.bat）
 6. 编写代码（复制 BSP 驱动、生成 main.c、ISR）
      ├── OLED/Keyboard: 硬件固定引脚，直接使用
      ├── 其他外设: 必须确认引脚！
      └── 涉及OLED: 必须检查显示逻辑(寻址模式/坐标系/帧率)！
 7. 代码质量检查（语法 / 逻辑 / 平台 三级）
 8. 编译  ←──────┐
 9. 修复错误 ─────┘
10. 烧录（工程创建时已自动配置 CMSIS-DAP）
11. 串口数据引擎（双向 / 同步）
12. HardFault 自动监控
13. 调试支持
```

> **最重要的规则**：第 7 步代码质量检查不可跳过。写完代码必须检查低级错误，不能看到"编译 0 错误"就以为任务完成。
> 
> **引脚确认铁律**：除 OLED 和 Keyboard 使用硬件固定引脚外，**任何其他外设（UART、ADC、PWM、I2C、SPI1、DAC、Timer、GPIO 等）在写入 syscfg 前必须用 AskUserQuestion 向用户确认引脚分配**。即使用户需求中没提引脚，也不能自己分配——必须问。违反此规则会导致引脚冲突或硬件损坏。

`{skill_dir}` = `~/.claude/skills/mspm0g3519`，下面所有命令都用这个变量。

---

## VREF 真实值校准

EVM 开发板的 VREF 标称 3.3V，但**实际测量值因板而异**（如本开发板实测 3.28V）。DAC/ADC 等依赖 VREF 的模拟外设计算时**必须使用实测值**：

```
DAC/DATA = 目标电压 × 4096 / VREF实测值
```

syscfg 中 `VREF.basicExtVolt` 和 `DAC12.dacOutput12` 均需按实测值调整。

> 使用 DAC/ADC 前提示用户：**"请用万用表实测 VREF 电压（PA23-VREFPOS vs PA21-VREFNEG），替换代码中的 VREF 标称值"**

## DAC 放大器驱动规则
> [!IMPORTANT]
> 在 SysConfig 中配置 DAC12 时，默认的输出缓冲放大器通常处于高阻抗（Tristate）关闭状态，这会导致 PA15 引脚无法输出物理电压。**必须确保 `DAC12.dacAmplifier = "ON"`**（脚本已被优化为默认开启），否则外部引脚无法测得电压。

## ADC 单次采样使能规则
> [!IMPORTANT]
> 当 ADC12 在单次转换（非 Repeat 模式）下工作时，每次转换完成加载结果后，ADC 硬件会自动关闭转换。**每次使用 `DL_ADC12_startConversion` 启动新的转换前，必须在软件中显式调用 `DL_ADC12_enableConversions` 重新开启转换触发**（例如在 Timer 中断或 ADC 中断中调用），否则 ADC 只会采样一次就会停滞。

---

## 硬件固定引脚（绝对不可修改）

以下引脚由开发板硬件决定，**任何情况下都不能修改**：

| 外设 | 引脚 | 说明 |
|------|------|------|
| OLED - SCLK | PB3 | SPI0 时钟，硬件连接 |
| OLED - MOSI | PB2 | SPI0 数据输出，硬件连接 |
| OLED - CS | PC9 | OLED 片选，硬件连接 |
| OLED - DC | PC8 | OLED 数据/命令选择，硬件连接 |
| OLED - RES | PB23 | OLED 复位，硬件连接 |
| Keyboard - H1~H4 | PB6, PB7, PB8, PB9 | 矩阵键盘行线 |
| Keyboard - V1~V4 | PB20, PB24, PB25, PB27 | 矩阵键盘列线 |
| Debug - SWCLK | PA20 | 调试时钟，系统保留 |
| Debug - SWDIO | PA19 | 调试数据，系统保留 |
| HFXT - HFXIN | PA5 | 外部 40MHz 晶振输入 |
| HFXT - HFXOUT | PA6 | 外部 40MHz 晶振输出 |

> 当用户需要使用 OLED 或 Keyboard 时，**必须使用上表的引脚**，不能自己分配。
> 其他外设分配引脚时也**不能与上表冲突**。

---

## 1. 确认需求

混合模式：
- 简单请求（"创建 LED 闪烁工程"）：一句话提取参数，全自动执行
- 复杂请求（多外设、自定义引脚、特殊时钟）：用 AskUserQuestion 收集

需要确认的信息：
- **工程名称** —— 英文名（如 `LED_Blink`、`UART_Echo`）
- **保存位置** —— 工程的父目录路径
- **外设需求** —— 需要哪些外设（OLED, UART, ADC, PWM, I2C, SPI, Timer, Keyboard 等）
- **具体配置** —— 波特率、采样率、PWM 频率等
- **引脚分配 [不可跳过]** —— OLED/Keyboard 用固定引脚直接使用；**其他所有外设必须用 AskUserQuestion 确认引脚**。即使用户没提引脚也要问，否则不能进入第 4 步修改 syscfg

---

## 2. 检查工具链

检查项：
1. Keil MDK-ARM（uv4.exe）—— 注册表、标准路径、PATH
2. MSPM0 SDK 2.08.00.03 —— 自动搜索 `D:\ti\`, `C:\ti\`, 环境变量等
3. SysConfig 1.25.0 —— 自动搜索 `D:\ti\`, `C:\ti\`, 环境变量等

### 2.1 自动搜索失败时 —— 询问用户

如果 SDK 或 SysConfig 自动搜索不到，**必须立即用 `AskUserQuestion` 询问用户路径**：

```
Q: "MSPM0 SDK 未自动检测到，请提供 SDK 路径"
   提供选项: "D:\ti\mspm0_sdk_2_08_00_03" / "C:\ti\mspm0_sdk_2_08_00_03" / "我自己输入路径"

Q: "SysConfig 未自动检测到，请提供 SysConfig 路径"
   提供选项: "D:\ti\sysconfig_1.25.0" / "C:\ti\sysconfig_1.25.0" / "我自己输入路径"
```

用户提供的路径需要验证：
- SDK：检查 `tools/keil/syscfg.bat` 和 `source/ti/driverlib/driverlib.h` 存在
- SysConfig：检查 `sysconfig_cli.bat` 存在

> **不要**跳过 SDK/SysConfig 检查直接创建工程。缺一不可。

---

## 3. 创建工程

```bash
python {skill_dir}/scripts/project_creator.py \
  --name {name} --path {path} --sdk-path {sdk_path}
```

`skeleton/empty/` 是一个**完整可编译的参考工程**，包含：
- **完整 DriverLib**（`Source/ti/driverlib/`，868 个文件）
- **CMSIS Core**（`Source/third_party/CMSIS/`）
- **BSP 驱动**：OLED（`BSP/OLED/spi0_oled.c`）、delay（`BSP/delay/delay.c`）、bsp.h
- **Keil 工程**：`Project/empty.uvprojx`，所有 .c 文件已添加
- **syscfg 配置**：`User/config.syscfg`（已配置 SPI0 + OLED GPIO + 40MHz HFXT）

流程：
1. 复制 `skeleton/empty/` 到目标路径（排除 Output/、.uvguix.*）
2. 重命名 `Project/empty.uvprojx` → `Project/{name}.uvprojx`
3. 文本替换 uvprojx 中的 TargetName、OutputName、syscfg.bat 路径
4. 修复 uvprojx 中的绝对路径（C:\... → ..\）
5. 生成 README.md（含固定引脚表）
6. smoke build 验证骨架完整性
7. **自动写入 `.uvoptx` CMSIS-DAP Debug 配置**（无需用户手动配置）

---

## 4. 修改 syscfg

这是最核心的步骤。配置外设和引脚通过修改 `User/config.syscfg` 实现。

### 4.1 查看当前配置

```bash
python {skill_dir}/scripts/syscfg_parser.py \
  --syscfg {project}/User/config.syscfg --list-modules
python {skill_dir}/scripts/syscfg_parser.py \
  --syscfg {project}/User/config.syscfg --list-pins
```

### 4.2 添加外设

```bash
python {skill_dir}/scripts/syscfg_parser.py \
  --syscfg {project}/User/config.syscfg \
  --add-peripheral '{"module":"/ti/driverlib/UART","instance":"UART_1",
    "name":"UART_0","baud":115200,"peripheral":"UART0","tx":"PA10","rx":"PA11"}'
```

### 4.3 删除外设

```bash
python {skill_dir}/scripts/syscfg_parser.py \
  --syscfg {project}/User/config.syscfg --remove-peripheral "UART_1"
```

### 4.4 修改时钟

```bash
python {skill_dir}/scripts/syscfg_parser.py \
  --syscfg {project}/User/config.syscfg \
  --modify-clock '{"node":"HFCLK4MFPCLKDIV","divideValue":5}'
```

### 4.5 检查引脚冲突

```bash
python {skill_dir}/scripts/syscfg_parser.py \
  --syscfg {project}/User/config.syscfg --check-conflicts
```

**硬件固定引脚强制规则**：
- 修改 OLED 或 Keyboard 的引脚 → **拒绝**，提示"此引脚由硬件固定，不可修改"
- 其他外设的引脚与固定引脚冲突 → **拒绝**，给出可用替代引脚列表
- OLED 和 Keyboard 的 syscfg 模块配置**必须与 hardware_pin_map.json 一致**

### 4.6 syscfg 属性顺序规则 **[关键]**

SysConfig 对 `.syscfg` 中属性的**书写顺序敏感**。顺序错误会导致引脚分配被**静默忽略**，SysConfig 自动分配随机引脚。

**GPIO 引脚的正确顺序**（`$name` 必须最先）：
```js
GPIO2.associatedPins[0].$name            = "H1";    // 1. $name 必须先
GPIO2.associatedPins[0].direction        = "INPUT";  // 2. direction (仅输入引脚)
GPIO2.associatedPins[0].internalResistor = "PULL_UP"; // 3. internalResistor
GPIO2.associatedPins[0].pin.$assign      = "PB6";    // 4. pin.$assign 最后
```

**外设实例的正确顺序**（`$name` 和 `peripheral.$assign` 必须最先）：
```js
SPI1.$name              = "SPI_0";       // 1. $name
SPI1.peripheral.$assign = "SPI0";        // 2. peripheral.$assign
SPI1.targetBitRate      = 20000000;      // 3. 其他属性
SPI1.frameFormat        = "MOTO3";
```

**验证方法**：生成 syscfg 后**必须检查** `ti_msp_dl_config.h` 中的引脚定义是否与预期一致：
```bash
grep "#define.*PORT\|#define.*PIN" {project}/User/ti_msp_dl_config.h | grep -i keyboard
```

> **违反此规则是导致"按键无反应"类 bug 的第一大原因。**

**多外设自动增量**：当用户说"再加一个 UART"，解析器自动检测已有 UART_0、UART_1...，创建下一个可用实例。

---

## 5. 生成 syscfg 代码

```bash
python {skill_dir}/scripts/syscfg_generator.py \
  --project-dir {project} --sdk-path {sdk_path}
```

运行 syscfg.bat → 检查 `ti_msp_dl_config.c` 和 `ti_msp_dl_config.h` 是否生成成功。

---

## 6. 编写代码

### 6.00 模块封装规范 **[必须遵循]**

每个外设必须封装为独立的 `.c`/`.h` 模块对，放在 `BSP/{MODULE}/` 目录下。ISR 放在对应的模块 `.c` 文件中，不放在 `main.c`。

**目录结构示例**：
```
BSP/
├── bsp.h                     # 总头文件, #include 所有模块头
├── delay/delay.c + delay.h    # 延时
├── OLED/spi0_oled.c + .h      # OLED 底层驱动
├── OLED_DRAW/oled_draw.c + .h # OLED 帧缓冲绘图
├── DAC0/dac0.c + dac0.h       # DAC 输出
├── ADC0/adc0.c + adc0.h       # ADC 采集 (含 ADC ISR)
├── KEY/key.c + key.h         # 按键 (含 GROUP1_IRQHandler)
└── WAVE/wave.c + wave.h      # 波形引擎 (DDS 相位累加器)
```

**模块设计规则**：
1. **ISR 就近原则**：哪个模块的外设中断，ISR 就放在该模块 `.c` 中。例如 `ADC0_IRQHandler` 在 `adc0.c`，`GROUP1_IRQHandler` 在 `key.c`
2. **共享状态集中**：多个模块共享的变量（如 `display_update`、`adc_buf`）定义在逻辑归属模块中，声明为 `extern`
3. **main.c 极简**：只需 `#include "bsp.h"`，调用各模块 `_init()`，while(1) 只做显示调度。不包含 ISR 和驱动逻辑
4. **bsp.h 汇聚**：所有模块头文件统一在 `bsp.h` 中 `#include`，业务代码只需 `#include "bsp.h"`

**main.c 模板**：
```c
#include "bsp.h"

int main(void) {
    SYSCFG_DL_init();
    OLED_Init();
    OLED_Clear();

    wave_init();    /* 波形引擎 */
    dac0_init();    /* DAC 输出 */
    adc0_init();    /* ADC 采集 */
    key_init();     /* 按键 */

    DL_TimerA_startCounter(TIMER_0_INST);

    while (1) {
        if (display_update) {
            display_update = false;
            /* 更新 OLED 显示 */
            OLED_ShowString(...);
            oled_draw_waveform(adc_buf, SAMPLE_COUNT);
        }
    }
}

/* Timer ISR (在 main.c 中直接调用 wave 引擎) */
void TIMA1_IRQHandler(void) {
    DL_TimerA_clearInterruptStatus(TIMER_0_INST, DL_TIMERA_INTERRUPT_LOAD_EVENT);
    wave_timer_isr();
}
```

### 6.0 模板内建驱动

骨架模板已内建以下 BSP 驱动，**无需额外复制**，可直接使用：

| 驱动 | 文件 | API |
|------|------|-----|
| OLED (SPI0) | `BSP/OLED/spi0_oled.c` | `OLED_Init()`, `OLED_Clear()`, `OLED_ShowString()`, `OLED_ShowChar()`, `OLED_ShowNum()`, `OLED_ShowCHinese()` |

> **OLED 控制器**：EVM 开发板使用 **SH1106**（非 SSD1306），SPI 模式必须为 **CPOL=1/CPHA=1**（`MOTO3_POL1_PHA1`）。模板的 `config.syscfg` 已配置正确。`OLED_Set_Pos` 中 `(x & 0x0f) | 0x01` 是 SH1106 列偏移 +2 的体现，不是 bug。
| delay | `BSP/delay/delay.c` | `delay_ms()`, `delay_us()`, `delay_s()` |
| bsp | `BSP/bsp.h` | `u8`/`u32` 类型定义，包含 OLED + delay 头文件 |

`BSP/bsp.h` 已经 `#include "delay.h"` 和 `#include "spi0_oled.h"`，main.c 只需 `#include "bsp.h"` 即可使用。

### 6.0.1 硬性要求：main.c 必须实现用户需求

模板的 main.c 有 OLED 演示代码。**绝对不允许**：
- 演示代码没改就直接编译烧录
- 看到"编译 0 错误"就报告任务完成
- while(1) 里是空的

进入第 8 步编译前，**必须**确认 main.c 至少包含：
1. `SYSCFG_DL_init()` 调用
2. 用户需求里所有外设的 `_init()` 调用
3. while(1) 里有**实际业务逻辑**（不能是空 `{}`）

### 6.0.2 OLED 显示逻辑检查 **[涉及 OLED 时必须执行]**

任何涉及 OLED 显示的代码，**写完必须逐项检查以下显示逻辑**：

**1. 寻址模式** — SH1106 页寻址模式（列地址从 0x02 开始，`OLED_Set_Pos` 中 `(x & 0x0f) | 0x01` 体现此偏移）。

**2. 文字布局规则 [关键]** — 8×16 字体(SIZE=16)每个字符占 **2 个 page**（16像素高）。
   - **行间隔必须 ≥2 pages**，否则上下行文字会互相覆盖。
   - 4 行文字的唯一安全布局：pages **0-1, 2-3, 4-5, 6-7**。
   - **不要在 page 7 放文字**：字符下半截(page 8)超出屏幕，显示不全。

**3. 水平边界 [关键]** — 每个字符 8px 宽。
   - **起始 x + 字符数 × 8 ≤ 128**，否则右侧字符超出屏幕。

**4. SH1106 列偏移 [信息]** — `OLED_Set_Pos` 中计算列地址时应直接通过 `x += 2;` 来偏移，而不是仅仅将最低位置 1 (`| 0x01`)。直接将最低位置 1 是原参考工程的严重 Bug，会导致 x=0 和 x=1 映射到同一列，使最左侧像素丢失！

**5. SPI 传输 BUSY 同步延迟 [关键]** — 任何自定义的 SPI 发送代码，如果使用 `DL_SPI_transmitData8`，**绝对不能**只用 `while (DL_SPI_isBusy())` 等待。因为 Cortex-M0+ 速度极快，写入 TX FIFO 后硬件 BUSY 标志可能延迟几个时钟周期才置位。必须双重检查：
```c
DL_SPI_transmitData8(SPI_0_INST, dat);
while (!DL_SPI_isTXFIFOEmpty(SPI_0_INST)) {} // 1. 先等 FIFO 为空
while (DL_SPI_isBusy(SPI_0_INST)) {}         // 2. 再等移位寄存器完成
delay_cycles(5);                             // 3. 补充极小延时满足 CS hold time
```
> **如果只等 isBusy 会导致 CPU 提前拉高 CS，截断最后一位数据，导致屏幕花屏或无响应。**

> **违反第 2、3 条是导致"内容重叠"和"内容溢出屏幕"类 bug 的第一大原因。违反第 5 条会导致驱动彻底失效。**

### 6.0.3 引脚确认规则

**OLED 和 矩阵键盘**的引脚由硬件固定，**不需要询问用户**，直接使用硬件固定引脚配置：

| 外设 | 固定引脚 |
|------|----------|
| OLED | SPI0: SCLK=PB3, MOSI=PB2, CS=PC9, DC=PC8, RES=PB23 |
| Keyboard | H1-4=PB6/7/8/9, V1-4=PB20/24/25/27 |

**其他外设**（UART, ADC, PWM, I2C, SPI1, Timer, GPIO 等），**编写代码前必须向用户确认引脚连接**。

### 6.1 按需复制 BSP 驱动

模板未包含的 BSP 驱动，从参考工程复制：

```bash
python {skill_dir}/scripts/code_writer.py --project-dir {project} \
  --add-bsp '["UART0","LED","KeyBoard","TimerG6_PWM_RGB"]'
```

从 `references/EVM_TEST_OLED/BSP/` 复制需要的 BSP 驱动到工程，更新 bsp.h 和 .uvprojx。

### 6.2 生成 main.c

```bash
python {skill_dir}/scripts/code_writer.py --project-dir {project} \
  --gen-main --requirements '{"UART0":{"baud":115200},"GPIO_LED":{"pins":["PA14"]}}'
```

生成规则：
- 初始化顺序：`SYSCFG_DL_init()` → 外设 `_init()` → while(1)
- while(1) 必须有实际逻辑
- 如果用到了中断，自动生成 ISR 函数

### 6.2.1 中断使能：外设 + NVIC 双重使能 **[极容易遗漏]**

**TI DriverLib 的 `DL_xxx_enableInterrupt()` 只使能外设内部的中断掩码 (IMASK)，不会使能 NVIC 侧中断。** 必须额外调用 `NVIC_EnableIRQ()`。

```c
// 错误：中断永远不会触发
DL_TimerG_enableInterrupt(TIMER_0_INST, DL_TIMERG_INTERRUPT_LOAD_EVENT);

// 正确：外设中断 + NVIC 中断都要打开
DL_TimerG_enableInterrupt(TIMER_0_INST, DL_TIMERG_INTERRUPT_LOAD_EVENT);
NVIC_EnableIRQ(TIMER_0_INST_INT_IRQN);  // 这行必须加！
```

**所有启用中断的外设（TIMER、UART、GPIO 等），SysConfig 生成 `_init()` 后，必须在 `main()` 中手动调用 `NVIC_EnableIRQ()`。**

常见的 IRQn 宏：
- SysConfig 生成的 `XXX_INST_INT_IRQN`（如 `TIMER_0_INST_INT_IRQN`、`UART_0_INST_INT_IRQN`）
- 外设手册中的 `XXX_INT_IRQn`（如 `TIMG7_INT_IRQn`、`UART0_INT_IRQn`）

检查方法：编译前在 main.c 中搜索 `DL_.*enableInterrupt`，每处都要有对应的 `NVIC_EnableIRQ`。

### 6.3 printf 重定向（可选）

```bash
python {skill_dir}/scripts/code_writer.py --project-dir {project} --add-printf
```

通过 UART0 实现 printf 重定向（fputc）。

### 风格规范
- 函数命名：`Module_Verb()`（如 `uart0_init()`, `adc0_read()`）
- 文件名：小写 + 下划线（`timerG6_pwm_rgb.c`）
- 头文件保护：`__MODULE_NAME_H__`
- 每个外设一对 .c/.h，放在 `BSP/` 下
- 中文注释

---

## 7. 代码质量检查 **[关键步骤，不可跳过]**

```bash
python {skill_dir}/scripts/code_checker.py --project-dir {project} --level 3
```

三级检查：

| 级别 | 检查内容 | 处理方式 |
|------|----------|----------|
| Level 1 语法 | 括号匹配、分号缺失、字符串未闭合、`#if`/`#endif` 配对、`#include` 文件存在性 | 自动修复 |
| Level 2 逻辑 | 未初始化变量、类型截断、死代码、空 while(1)、函数声明缺失 | 报告 + 部分自动修复 |
| Level 3 平台 | **NVIC 使能匹配（所有 `DL_xxx_enableInterrupt` 必须有对应 `NVIC_EnableIRQ`）**、GPIO 引脚有效性、时钟初始化顺序、`SYSCFG_DL_init()` 唯一调用、固定引脚验证 | 报告 |

**检查不通过不能进入编译步骤**。Level 1 错误全部自动修复后再编译。

---

## 8. 编译

```bash
python {skill_dir}/scripts/keil_builder.py --project {project}/Project/{name}.uvprojx
```

解析 ARMCLANG V6.24 格式的编译输出，展示 Flash/RAM 占用率：
```
编译成功！
0 个错误, 2 个警告
占用: Flash=24.5 KB / 512.0 KB (4.8%), RAM=8.2 KB / 128.0 KB (6.4%)
```

MSPM0G3519 内存布局：
- Flash: 512KB (0x00000000, 0x80000)
- RAM: Bank0=64KB + Bank1=64KB = 128KB total

---

## 9. 自动修复编译错误

全自动模式（无需用户确认），最多 5 轮 "编译 → 修复 → 编译"：

```bash
python {skill_dir}/scripts/error_fixer.py \
  --errors '{json_array}' --project-dir {project} --apply
```

MSPM0 常见错误自动修复：
- `ti_msp_dl_config.h not found` → 运行 syscfg 生成
- `DL_xxx undefined` → 添加对应 `dl_xxx.c` 到 .uvprojx
- `use of undeclared identifier` → 搜索 DriverLib/BSP 头文件并添加 `#include`
- `unknown type name 'u8'` → 确保 `bsp.h` 被包含

第 5 轮还失败 → 把剩余错误抛给用户。

---

## 10. 烧录

编译成功后清理中间文件，然后直接烧录（工程创建时已自动配置 CMSIS-DAP，无需手动设置）：

```bash
# 清理编译中间文件 (保留 .hex/.axf)
rm -f {project}/Output/*.o {project}/Output/*.d

# 烧录
python {skill_dir}/scripts/flasher.py --project {project}/Project/{name}.uvprojx
```

成功标志：`Erase Done. Programming Done. Verify OK. Application running ...`

### 烧录失败处理

如果 `uv4 -f` 失败（如 "Target DLL cancelled"），按以下顺序排查：
1. 运行 `uvprojx_modifier.py debug-config` 重新生成 `.uvoptx`
2. 确认 Keil DFP 和 `MSPM0GX51X_MAIN_512KB.FLM` 已安装
3. 在 Keil 中手动选择 CMSIS-DAP → Flash Download 勾选 Reset and Run → OK → 重试

---

## 11. 串口数据引擎

```bash
# 列出可用串口
python {skill_dir}/scripts/serial_bridge.py --list

# 启动后台守护（UART0 默认 PA10=TX, PA11=RX, 115200）
python {skill_dir}/scripts/serial_bridge.py --port COMx --baud 115200 &

# 读取输出
python {skill_dir}/scripts/serial_bridge.py --tail 30 --parse

# 发送命令
python {skill_dir}/scripts/serial_bridge.py --send "AT+VALUE=100"
```

---

## 12. HardFault 自动监控

使用前需要：板子代码中已加入 HardFault_Handler 寄存器转储 + 串口已初始化。

```bash
python {skill_dir}/scripts/hardfault_watcher.py \
  --port COMx --baud 115200 \
  --map {project}/Project/Listings/{name}.map
```

Cortex-M0+ 只有 HardFault（无 UsageFault/BusFault/MemManage），分析器解析寄存器转储格式：

```
HardFault
R0=0x20001234 R1=0xDEADBEEF R2=... R3=...
R12=... LR=... PC=0x00001234 xPSR=...
CFSR=0x00000001 HFSR=0x40000000
```

---

## 13. 调试支持

- Keil 中 `Ctrl+F5` 启动调试
- F9 断点，F10 单步跨过，F11 单步进入
- 调试器：CMSIS-DAP，SWD，SWCLK=PA20，SWDIO=PA19

---

## MSPM0 常见外设避坑铁律

为防止生成其他外设代码时发生低级硬件逻辑错误，任何时候编写 MSPM0 代码必须满足以下铁律：

### 1. I2C 总线避坑
> [!CAUTION]
> **SDA/SCL 引脚上拉**：I2C 物理总线为开漏输出。如果在 `config.syscfg` 中添加 I2C 模块，且外围硬件没有物理上拉电阻，**必须**在 `config.syscfg` 的关联引脚属性中将 SCL/SDA 配置为内部上拉：
> `internalResistor = "PULL_UP"`
> 否则，I2C 链路会始终读取到低电平，通信将永久死锁在 Busy 状态。

### 2. 定时器与 PWM 避坑
> [!IMPORTANT]
> **显式启动计数**：通过 SysConfig 生成的定时器（TIMG/TIMA）或 PWM 初始化代码，仅使能了时钟与中断，但**没有开启计数器**。
> 必须在 `main` 函数初始化完毕后，显式调用启动宏：
> `DL_TimerG_startCounter(TIMER_0_INST);` 或 `DL_TimerA_startCounter(TIMAx);`
> 否则，定时器或 PWM 永远不会工作，中断也永远不会触发。

### 3. GPIO 中断死循环避坑
> [!CAUTION]
> **手动清除中断标志**：在编写 `GROUP1_IRQHandler` 等 GPIO 外部中断服务函数（如按键、外部脉冲计数）时，处理完业务逻辑后，**必须**在 ISR 退出前显式清除引脚的中断标志位：
> `DL_GPIO_clearInterruptStatus(KEY_PORT, KEY_BTN_PIN);`
> 否则，Cortex-M0+ 核心退出中断后会因标志位仍未被清除而立刻再次触发中断，使 CPU 陷入无限的中断死循环，表现为系统彻底卡死。

### 4. 模拟外设 (ADC / DAC) 避坑
> [!IMPORTANT]
> - **DAC 放大器（Amplifier）使能**：配置 DAC12 输出时，必须添加 `DAC12.dacAmplifier = "ON";`（脚本已作自动修改）。否则输出管脚 PA15 处于高阻抗三态（Tristate），不输出电压。
> - **ADC 单次采样重新使能**：如果 ADC12 处于单次非 Repeat 转换模式下，每次数据转换完成后，硬件通道会自动关闭。在下一次调用 `DL_ADC12_startConversion()` 之前，**必须先执行 `DL_ADC12_enableConversions(ADC0_INST);`**。
> - **ADC 采样时间配置**：添加 ADC 外设后，必须显式调用 `DL_ADC12_setSampleTime0(ADC0_INST, 500);` 设定采样保持时间（如 500 个时钟周期），防止采样电容充电不足导致测量数据严重偏低或产生波形畸变。

### 5. SPI 硬件同步延迟避坑
> [!WARNING]
> - **双重忙等待**：在操作 SPI 传输并控制片选（CS）拉高时，绝对不能仅轮询 `DL_SPI_isBusy`，必须严格执行：
>   1. 等待发送 FIFO 为空 (`!DL_SPI_isTXFIFOEmpty`)
>   2. 等待移位寄存器非 Busy (`DL_SPI_isBusy`)
>   3. 延迟 5~10 个时钟周期（CS Hold Time）再拉高 CS 引脚。
>   否则会因为 CPU 频率远高于 SPI 时钟，导致在最后一字节未发完前被 CPU 提前拉高 CS，数据被截断花屏。

### 6. 定时器 ISR 频率与 CPU 饥饿避坑 **[极容易遗漏]**
> [!CAUTION]
> **定时器中断频率不能过高，必须预留主循环 CPU 时间**。
>
> Cortex-M0+ 主频 80MHz，ISR 入口+退出约 12+12=24 周期，加上业务逻辑。**当定时器周期接近 ISR 总执行时间时，CPU 将 100% 被 ISR 占用，主循环（while(1)）彻底饿死，表现为主循环代码根本不执行（屏幕不刷新、按键无反应等）。**
>
> **铁律**：定时器周期（CPU 周期数）≥ ISR 总执行时间 × 1.5。
> - 200kHz 定时器（400 CPU 周期）：ISR ~70 周期 → 安全（17% CPU）
> - 1MHz 定时器（80 CPU 周期）：ISR ~70 周期 → 饥饿！（87% CPU，主循环饿死）
>
> **高频输出**（如 100kHz DAC 波形）不应靠提高定时器频率实现，应使用 **DDS 相位累加器** 方案：定时器保持中低频率（如 200kHz），在 ISR 内用 32 位相位累加器计算输出值，通过改变相位步进值 `phase_increment` 来调节输出频率，而不是改变定时器频率。
>
> ```c
> // 正确: 固定 200kHz 定时器 + DDS 相位累加器
> phase_accum += phase_increment;          // phase_increment 随频率变化
> uint16_t idx = (uint16_t)(phase_accum >> 25);  // 128 点查表
> dac0_output(sine_table[idx]);
>
> // 错误: 用 1MHz 定时器驱动 DAC（主循环饿死！）
> ```

---

## 目录结构

```
{skill_dir}/
├── SKILL.md                    # 本文件
├── README.md                   # 安装与使用说明
├── requirements.txt            # Python 依赖 (pyserial)
├── chip_db.json                # MSPM0G3519 芯片规格
├── references/
│   ├── error_patterns.json     # ARMCLANG V6.24 编译错误模式库
│   ├── hardware_pin_map.json   # 硬件固定引脚定义
│   ├── peripheral_db.json      # 外设→引脚→配置映射
│   ├── sdk_paths.json          # SDK/SysConfig 搜索路径
│   ├── clock_tree_ref.json     # MSPM0G3519 时钟树参考
│   ├── bsp_index.json          # 外设→BSP模块→syscfg模块索引
│   └── EVM_TEST_OLED/          # 完整参考工程（所有外设 BSP 驱动 + syscfg + main.c）
│       ├── BSP/                #   14 个外设 BSP 驱动模块
│       ├── User/               #   config.syscfg (393行, 17个模块实例)
│       ├── Project/            #   Keil 工程文件
│       └── keilkill.bat
├── skeleton/
│   └── empty/                  # 完整可编译模板（含 DriverLib 868 文件 + OLED/delay BSP + CMSIS）
└── scripts/
    ├── utils.py                # 共享工具
    ├── sdk_detector.py         # 自动检测 SDK + SysConfig
    ├── project_creator.py      # 创建工程（拷贝骨架 + 改名 + 修复路径 + CMSIS-DAP配置）
    ├── driverlib_manager.py    # DriverLib 列表（legacy，模板已内建 DriverLib）
    ├── uvprojx_modifier.py     # 修改 .uvprojx XML
    ├── syscfg_parser.py        # 解析+修改 .syscfg JS
    ├── syscfg_generator.py     # 运行 sysconfig_cli.bat 生成 C 代码
    ├── code_writer.py          # 复制 BSP + 生成 main.c（模板内建驱动自动跳过）
    ├── code_checker.py         # 三级代码质量检查
    ├── keil_builder.py         # 编译
    ├── error_fixer.py          # 自动修复编译错误
    ├── flasher.py              # 烧录
    ├── serial_bridge.py        # 串口数据引擎
    ├── serial_monitor.py       # 串口前台监控
    ├── hardfault_analyzer.py   # HardFault 分析
    ├── hardfault_watcher.py    # HardFault 自动捕获
    └── clock_calculator.py     # 时钟树计算
```
