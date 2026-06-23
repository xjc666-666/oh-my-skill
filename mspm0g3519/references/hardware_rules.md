# MSPM0G3519 Hardware Rules

Use this file whenever a task touches pins, board wiring, OLED, matrix keyboard, ADC, DAC, VREF, clock, flash/debug wiring, or external modules.

## Fixed Pins

These pins are fixed by the development board. Never move them in SysConfig or generated code.

| Function | Pin | Rule |
|---|---:|---|
| OLED SPI0 SCLK | PB3 | Fixed |
| OLED SPI0 MOSI | PB2 | Fixed |
| OLED CS | PC9 | Fixed GPIO |
| OLED DC | PC8 | Fixed GPIO |
| OLED RES | PB23 | Fixed GPIO |
| Keyboard H1-H4 | PB6, PB7, PB8, PB9 | Fixed matrix rows |
| Keyboard V1-V4 | PB20, PB24, PB25, PB27 | Fixed matrix columns |
| SWD SWCLK | PA20 | Reserved for debug |
| SWD SWDIO | PA19 | Reserved for debug |
| HFXT HFXIN | PA5 | 40 MHz crystal |
| HFXT HFXOUT | PA6 | 40 MHz crystal |

`references/hardware_pin_map.json` is the structured source of truth. If prose and JSON disagree, inspect hardware and update both.

## Pin Confirmation Rule

- OLED and Keyboard use the fixed pins above without asking the user.
- Every other peripheral needs explicit pin confirmation before editing `User/config.syscfg`: UART, ADC, DAC, PWM, Timer, GPIO, I2C, SPI1, W25Q64, IMU, buzzer, LED, and custom modules.
- Do not silently choose "default" pins from examples. The example wiring is only a hint unless the user confirms it matches the board.
- Reject any requested assignment that conflicts with fixed or reserved pins.

## VREF and Analog Work

The EVM nominal VREF is 3.3 V, but analog calculations must use the measured board value.

Before ADC or DAC voltage work, ask the user to measure VREF between PA23 VREFPOS and PA21 VREFNEG. Use the measured value in formulas and SysConfig:

```text
DAC_DATA = target_voltage * 4096 / measured_vref
```

Check `VREF.basicExtVolt` and `DAC12.dacOutput12` after editing SysConfig.

## Clock and Debug Pins

- Keep PA5/PA6 reserved for the 40 MHz HFXT path unless the user explicitly changes board hardware.
- Keep PA19/PA20 reserved for SWD. Do not reuse them for GPIO or external modules.
- If flashing or debug fails, verify power, USB cable, SWD wiring, Keil Debug selection, Flash Download algorithm, and Reset and Run before changing firmware logic.
