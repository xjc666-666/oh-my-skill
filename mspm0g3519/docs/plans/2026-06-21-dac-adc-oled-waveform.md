# DAC_ADC_OLED_Waveform 实现计划

> **For agentic workers:** 按照 mspm0g3519 skill 流程逐步执行此计划。

**Goal:** 在 MSPM0G3519 上实现 DAC 产生正弦波/矩形波/三角波（1KHz），ADC 采集波形并显示在 OLED 上，PB31 按键切换波形类型。

**Architecture:** Timer 中断驱动 DAC 输出（80KHz 更新率，128 点/周期 = 1KHz），ADC 同步采集 DAC 输出存入缓冲区，主循环将缓冲区波形绘制到 OLED 128x64 屏幕上。按键 PB31 外部中断切换波形类型。

**Tech Stack:** MSPM0G3519 (Cortex-M0+), TI DriverLib, Keil MDK-ARM V6.24, SysConfig 1.25.0, MSPM0 SDK 2.08.00.03

---

## 硬件连接

| 信号 | 引脚 | 说明 |
|------|------|------|
| DAC 输出 | PA15 | DAC0 固定输出引脚 |
| ADC 输入 | PA27 | ADC0 通道 0（用户确认） |
| 按键 | PB31 | GPIO 输入，下降沿中断，内部上拉 |
| OLED SCLK | PB3 | SPI0 时钟（硬件固定） |
| OLED MOSI | PB2 | SPI0 数据（硬件固定） |
| OLED CS | PC9 | 片选（硬件固定） |
| OLED DC | PC8 | 数据/命令（硬件固定） |
| OLED RES | PB23 | 复位（硬件固定） |
| VREF | VDDA | 用户选择使用 VDDA 作为参考电压 |

**重要：需要杜邦线连接 PA15（DAC 输出）→ PA27（ADC 输入）**

---

## 定时器计算

- 系统时钟: 80MHz (40MHz HFXT × PLL ×4 / /2)
- 波形频率: 1KHz，每周期 128 点
- Timer 中断频率: 1KHz × 128 = 128KHz
- TIMG 配置: busclk=80MHz, div=1 → 40MHz, prescale=1 → 20MHz
  - period = 20MHz / 128KHz - 1 = 155（ARR=155）
- 实际频率: 20MHz / (155+1) = 128.205KHz ≈ 128KHz ✓

---

## 文件结构

```
D:\workspace_for_claude\keil_for_claude\DAC_ADC_OLED_Waveform\
├── BSP/
│   ├── ADC0/adc0.c, adc0.h          (从参考工程复制)
│   ├── KEY/key.c, key.h              (从参考工程复制，修改为 PB31)
│   ├── OLED/spi0_oled.c, spi0_oled.h, spi0_oledfont.h, oledfont_bmp.h  (模板内建)
│   ├── delay/delay.c, delay.h        (模板内建)
│   └── bsp.h                         (模板内建，需添加 ADC0/KEY 头文件)
├── User/
│   ├── config.syscfg                 (修改：添加 DAC/ADC/GPIO/Timer)
│   ├── ti_msp_dl_config.c/h          (syscfg 生成)
│   ├── main.c                        (编写：波形生成 + ADC采集 + OLED显示)
│   └── wavegen.c, wavegen.h          (新建：波形 LUT + DAC 驱动)
├── Source/ti/driverlib/               (模板内建)
├── Project/
│   └── DAC_ADC_OLED_Waveform.uvprojx (模板改名)
└── README.md
```

---

## Task 1: 创建工程骨架

**Files:**
- Create: `D:\workspace_for_claude\keil_for_claude\DAC_ADC_OLED_Waveform\` (整个目录)

```bash
python {skill_dir}/scripts/project_creator.py \
  --name DAC_ADC_OLED_Waveform \
  --path "D:\workspace_for_claude\keil_for_claude" \
  --sdk-path "D:\ti\mspm0_sdk_2_08_00_03" \
  --smoke-build
```

---

## Task 2: 修改 SysCfg 配置

**Files:**
- Modify: `User/config.syscfg`

需要添加的外设模块：
1. **DAC12** — DAC0, PA15 输出, VDDA 参考
2. **ADC12 (ADC0)** — 单通道, PA27 (通道 0), 单次转换模式
3. **GPIO (key)** — PB31, 输入, 下降沿中断, 内部上拉
4. **TIMER** — 用于 128KHz 定时中断驱动 DAC 更新
5. **VREF** — 使能, 使用 VDDA（basicMode = DL_VREF_ENABLE_DISABLE）

修改要点：
- 保留 OLED (SPI0)、OLED GPIO、键盘 GPIO、LED GPIO、UART0 的原有配置
- 添加 DAC12 模块：dacPosVREF="VDDA", dacOutputPinEn=true
- 添加 ADC12 实例：单通道 PA27, 单次转换, MEM0
- 添加 GPIO 实例：key2 (PB31), INPUT, FALL, PULL_UP
- 添加 TIMER 实例：用于 128KHz 中断

```bash
python {skill_dir}/scripts/syscfg_parser.py \
  --syscfg {project}/User/config.syscfg \
  --add-peripheral '{"module":"/ti/driverlib/DAC12","name":"DAC12","dacPosVREF":"VDDA","dacOutputPinEn":true,"dacAmplifier":"ON"}'

python {skill_dir}/scripts/syscfg_parser.py \
  --syscfg {project}/User/config.syscfg \
  --add-peripheral '{"module":"/ti/driverlib/ADC12","instance":"ADC0","name":"ADC0","mode":"single","adcPin0":"PA27"}'

python {skill_dir}/scripts/syscfg_parser.py \
  --syscfg {project}/User/config.syscfg \
  --add-peripheral '{"module":"/ti/driverlib/GPIO","name":"key2","pins":[{"name":"btn","direction":"INPUT","polarity":"FALL","resistor":"PULL_UP","pin":"PB31"}]}'
```

---

## Task 3: 生成 SysCfg 代码

```bash
python {skill_dir}/scripts/syscfg_generator.py \
  --project-dir {project} \
  --sdk-path "D:\ti\mspm0_sdk_2_08_00_03"
```

验证 `ti_msp_dl_config.h` 中生成：
- `DAC12_INT_IRQN`, `GPIO_DAC12_OUT_PIN`
- `ADC0_INST`, `ADC0_ADCMEM_0`
- `key2_PORT`, `key2_btn_PIN`

---

## Task 4: 复制 BSP 驱动

```bash
python {skill_dir}/scripts/code_writer.py --project-dir {project} \
  --add-bsp '["ADC0","KEY"]'
```

复制文件：
- `references/EVM_TEST_OLED/BSP/ADC0/adc0.c` → `{project}/BSP/ADC0/`
- `references/EVM_TEST_OLED/BSP/ADC0/adc0.h` → `{project}/BSP/ADC0/`
- `references/EVM_TEST_OLED/BSP/KEY/key.c` → `{project}/BSP/KEY/`
- `references/EVM_TEST_OLED/BSP/KEY/key.h` → `{project}/BSP/KEY/`

修改 `bsp.h` 添加：
```c
#include "ADC0/adc0.h"
#include "KEY/key.h"
```

---

## Task 5: 创建波形生成模块

**Files:**
- Create: `User/wavegen.h`
- Create: `User/wavegen.c`

### wavegen.h
```c
#ifndef __WAVEGEN_H__
#define __WAVEGEN_H__

#include "bsp.h"

#define WAVE_POINTS     128     /* 每周期采样点数 */
#define WAVE_AMP_MAX    4095    /* 12-bit DAC 满量程 */
#define WAVE_AMP_MID    2048    /* 中间值 */

typedef enum {
    WAVE_SINE = 0,
    WAVE_SQUARE,
    WAVE_TRIANGLE,
    WAVE_TYPE_COUNT
} WaveType_t;

extern volatile WaveType_t g_currentWave;
extern volatile uint16_t g_waveTable[WAVE_POINTS];
extern volatile uint8_t g_waveIndex;

void WaveGen_Init(void);
void WaveGen_SetType(WaveType_t type);
void WaveGen_FillTable(WaveType_t type);

#endif
```

### wavegen.c
```c
#include "wavegen.h"
#include <math.h>

#define PI 3.14159265f

volatile WaveType_t g_currentWave = WAVE_SINE;
volatile uint16_t g_waveTable[WAVE_POINTS];
volatile uint8_t g_waveIndex = 0;

void WaveGen_FillTable(WaveType_t type)
{
    for (int i = 0; i < WAVE_POINTS; i++) {
        switch (type) {
            case WAVE_SINE:
                /* 正弦波: 0~4095 */
                g_waveTable[i] = (uint16_t)(WAVE_AMP_MID +
                    WAVE_AMP_MID * sinf(2.0f * PI * i / WAVE_POINTS));
                break;
            case WAVE_SQUARE:
                /* 矩形波: 前半周期高，后半周期低 */
                g_waveTable[i] = (i < WAVE_POINTS / 2) ?
                    WAVE_AMP_MAX : 0;
                break;
            case WAVE_TRIANGLE:
                /* 三角波: 线性上升再下降 */
                if (i < WAVE_POINTS / 2)
                    g_waveTable[i] = (uint16_t)(2 * WAVE_AMP_MAX * i / WAVE_POINTS);
                else
                    g_waveTable[i] = (uint16_t)(2 * WAVE_AMP_MAX * (WAVE_POINTS - 1 - i) / WAVE_POINTS);
                break;
            default:
                g_waveTable[i] = WAVE_AMP_MID;
                break;
        }
    }
}

void WaveGen_Init(void)
{
    g_currentWave = WAVE_SINE;
    g_waveIndex = 0;
    WaveGen_FillTable(g_currentWave);
}

void WaveGen_SetType(WaveType_t type)
{
    if (type < WAVE_TYPE_COUNT) {
        g_currentWave = type;
        WaveGen_FillTable(type);
        g_waveIndex = 0;
    }
}
```

---

## Task 6: 编写 main.c

**Files:**
- Modify: `User/main.c`

```c
#include "bsp.h"
#include "wavegen.h"

/* ADC 采集缓冲区 */
volatile uint16_t g_adcBuffer[WAVE_POINTS];
volatile uint8_t g_adcReady = 0;      /* ADC 采集完成标志 */
volatile uint8_t g_displayUpdate = 0;  /* 显示更新标志 */

/* 波形名称 */
const char *waveNames[] = {"Sine", "Square", "Triangle"};

/* 按键标志（由 key.c 中断设置） */
extern uint8_t key_flag;

/* Timer 中断：驱动 DAC 输出 + 触发 ADC 采集 */
void TIMG8_IRQHandler(void)
{
    DL_TimerG_clearInterrupt(TIMER_0_INST, DL_TIMERG_INTERRUPT_LOAD_EVENT);

    /* 更新 DAC 输出 */
    DL_DAC12_output12(DAC0, g_waveTable[g_waveIndex]);

    /* 启动 ADC 采集 */
    DL_ADC12_enableConversions(ADC0_INST);
    DL_ADC12_startConversion(ADC0_INST);

    /* 记录当前点索引（ADC 完成中断中使用） */
    g_waveIndex = (g_waveIndex + 1) % WAVE_POINTS;
}

/* ADC 中断：读取结果存入缓冲区 */
void ADC0_INST_IRQHandler(void)
{
    switch (DL_ADC12_getPendingInterrupt(ADC0_INST)) {
        case DL_ADC12_IIDX_MEM0_RESULT_LOADED: {
            uint16_t val = DL_ADC12_getMemResult(ADC0_INST, DL_ADC12_MEM_IDX_0);
            uint8_t idx = (g_waveIndex == 0) ? (WAVE_POINTS - 1) : (g_waveIndex - 1);
            g_adcBuffer[idx] = val;
            if (idx == WAVE_POINTS - 1) {
                g_adcReady = 1;
            }
            break;
        }
        default:
            break;
    }
}

/* 波形显示 */
void Display_Waveform(void)
{
    OLED_Clear();

    /* 显示波形类型名称 */
    OLED_ShowString(0, 0, (char *)waveNames[g_currentWave], 16);

    /* 绘制波形 */
    for (int x = 0; x < 128; x++) {
        /* ADC 值 0~4095 映射到 y 像素 63~16（留出顶部文字空间） */
        uint8_t y = 63 - (uint8_t)((uint32_t)g_adcBuffer[x] * 47 / 4095);
        if (y < 16) y = 16;
        if (y > 63) y = 63;
        OLED_DrawPoint(x, y, 1);
    }

    /* 绘制基线 */
    for (int x = 0; x < 128; x++) {
        OLED_DrawPoint(x, 40, 1);  /* 中间基线 */
    }
}

int main(void)
{
    SYSCFG_DL_init();

    /* 初始化模块 */
    WaveGen_Init();
    adc0_init();

    /* 使能 Timer 中断 */
    NVIC_EnableIRQ(TIMER_0_INST_INT_IRQN);

    /* 使能 DAC */
    DL_DAC12_enable(DAC0_INST);
    DL_DAC12_enableOutputPin(DAC0_INST);

    /* 初始显示 */
    OLED_Clear();
    OLED_ShowString(0, 0, "DAC Wave Gen", 16);
    OLED_ShowString(0, 2, "1KHz", 16);
    delay_ms(1000);

    uint8_t lastKey = 0;

    while (1) {
        /* 按键处理：切换波形 */
        if (key_flag != lastKey) {
            lastKey = key_flag;
            WaveType_t next = (WaveType_t)((g_currentWave + 1) % WAVE_TYPE_COUNT);
            WaveGen_SetType(next);
        }

        /* ADC 数据就绪时更新显示 */
        if (g_adcReady) {
            g_adcReady = 0;
            Display_Waveform();
        }
    }
}
```

---

## Task 7: 修改 key.c 适配 PB31

**Files:**
- Modify: `BSP/KEY/key.c`

根据 syscfg 生成的宏名调整 key.c 中的中断处理：
- 使用 `key2_PORT`, `key2_btn_PIN`, `key2_btn_IIDX`
- 使用 `key2_INT_IRQN`（GPIOB_INT_IRQn）

```c
void GROUP1_IRQHandler(void)
{
    uint32_t flags = DL_GPIO_getEnabledInterruptStatus(key2_PORT, key2_btn_PIN);
    if (flags & key2_btn_PIN) {
        key_flag = !key_flag;
        DL_GPIO_clearInterruptStatus(key2_PORT, key2_btn_PIN);
    }
}
```

---

## Task 8: 代码质量检查

```bash
python {skill_dir}/scripts/code_checker.py --project-dir {project} --level 3
```

检查项：
- NVIC 使能匹配：TIMER_0 和 ADC0 的 `DL_xxx_enableInterrupt` + `NVIC_EnableIRQ`
- GPIO 引脚有效性：PB31 在可用引脚列表中
- DAC/ADC 初始化顺序正确
- OLED 寻址模式：页寻址，文字在 pages 0-1，波形在 pages 2-7

---

## Task 9: 编译

```bash
python {skill_dir}/scripts/keil_builder.py --project {project}/Project/DAC_ADC_OLED_Waveform.uvprojx
```

---

## Task 10: 烧录

```bash
python {skill_dir}/scripts/flasher.py --project {project}/Project/DAC_ADC_OLED_Waveform.uvprojx
```

---

## OLED 显示逻辑检查

1. **寻址模式**: SSD1306 页寻址（模板默认）
2. **文字布局**: 波形名称在 pages 0-1（y=0），波形绘制在 pages 2-7（y=16~63）
3. **水平边界**: x=0~127，字符数×8 ≤ 128
4. **波形映射**: ADC 0~4095 → y 63~16（47 像素高度），留出顶部 16 像素给文字

---

## 依赖关系

```
Task 1 (创建骨架) → Task 2 (修改 syscfg) → Task 3 (生成代码) → Task 4 (复制 BSP) → Task 5 (波形模块) → Task 6 (main.c) → Task 7 (key.c) → Task 8 (质量检查) → Task 9 (编译) → Task 10 (烧录)
```
