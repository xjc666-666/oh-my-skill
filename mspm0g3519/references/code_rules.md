# Code Rules

Use this file when writing or reviewing `main.c`, BSP drivers, interrupt handlers, OLED display logic, UART printf, timers, or application behavior.

## Main Application Rules

- `main.c` must call `SYSCFG_DL_init()` exactly once.
- Initialize user-required BSP/peripheral modules after `SYSCFG_DL_init()`.
- Keep `main.c` as a thin scheduler: call module init/task APIs, but put feature logic in `.c/.h` modules.
- `while (1)` must contain real requested behavior. Empty loops and unchanged template demos are not finished work.
- Do not report success from "0 build errors" alone. Verify runtime intent where possible.

## BSP Modules

The skeleton already includes:

| Module | Files | Typical API |
|---|---|---|
| OLED | `BSP/OLED/spi0_oled.*` | `OLED_Init()`, `OLED_Clear()`, `OLED_ShowString()` |
| delay | `BSP/delay/delay.*` | `delay_ms()`, `delay_us()`, `delay_s()` |
| bsp | `BSP/bsp.h` | Common types and includes |

For optional BSP modules, copy from `references/EVM_TEST_OLED/BSP/` through `code_writer.py` so `.uvprojx` and `bsp.h` stay synchronized:

```bash
python {skill_dir}/scripts/code_writer.py --project-dir {project} \
  --add-bsp '["UART0","LED","KeyBoard","TimerG6_PWM_RGB"]'
```

Use `references/bsp_index.json` to map features to BSP folders, SysConfig modules, init calls, and headers.

## Interrupt Rule

TI DriverLib interrupt enable calls only enable the peripheral-side interrupt mask. NVIC must be enabled separately.

```c
DL_TimerG_enableInterrupt(TIMER_0_INST, DL_TIMERG_INTERRUPT_LOAD_EVENT);
NVIC_EnableIRQ(TIMER_0_INST_INT_IRQN);
```

Before build, search for every `DL_.*enableInterrupt` and verify a matching `NVIC_EnableIRQ`.

## OLED Layout Rules

The built-in OLED driver targets an SH1106-style page display.

- Keep `BSP/OLED/spi0_oled.*` identical to the stable reference driver unless the user explicitly asks for driver work.
- Put app-specific OLED screens, wave buffers, graphs, and refresh policies in `Drive/<feature>.c/.h`; do not add `OLED_ClearWaveBuf()`-style application APIs to the BSP driver.
- 8x16 text consumes 2 pages per line.
- Safe 4-line layout is pages `0, 2, 4, 6`.
- `OLED_ShowString(x, y, ...)`, `OLED_ShowChar(x, y, ...)`, `OLED_ShowNum(x, y, ...)`, and `OLED_ShowCHinese(x, y, ...)` take `y` as a page index, not a pixel row. Values like `16` or `32` are invalid.
- Do not start 8x16 text at page 7.
- Horizontal bound is `x + characters * 8 <= 128`.
- For full-screen refreshes, write page by page. Do not assume column wrap advances page automatically.

If text overlaps, clips, or appears shifted, inspect `OLED_Set_Pos`, page selection, column low/high address bits, and text length before changing SPI timing.

## Code Quality Gate

Run before building:

```bash
python {skill_dir}/scripts/code_checker.py --project-dir {project} --level 3
```

Level 3 must cover:

- `SYSCFG_DL_init()` presence and uniqueness.
- Empty `while(1)` detection.
- Fixed pin validation.
- Reserved pin conflict detection.
- NVIC matching for DriverLib interrupt enables.

## Style

- Keep one BSP module per peripheral under `BSP/<module>/`.
- Keep public prototypes in `.h` and implementation in `.c`.
- Add every new `.c` file to the Keil `.uvprojx`.
- Prefer parseable runtime logs for debug, for example `BOOT_OK project=Name` and `ERR code=UART_TIMEOUT`.
