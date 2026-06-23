# Peripheral Templates

Use `scripts/peripheral_templates.py` before hand-writing common driver files.

## Commands

List available templates:

```bash
python {skill_dir}/scripts/peripheral_templates.py --list
```

Emit a driver pair and add it to Keil:

```bash
python {skill_dir}/scripts/peripheral_templates.py \
  --project {project_root} --uvprojx {uvprojx} \
  --peripheral USART --family F407 --module usart_debug
```

Emit the serial debug protocol:

```bash
python {skill_dir}/scripts/peripheral_templates.py \
  --project {project_root} --uvprojx {uvprojx} \
  --peripheral DEBUG_PROTOCOL --family F407 --module debug_protocol
```

## Rules

- Confirm pins before finalizing driver code.
- Use template output as a starting point, then adapt ports, pins, timers, DMA streams, and interrupt names to the actual board.
- For HAL-only families, prefer CubeMX-generated init when available, then use templates for higher-level module wrappers.
- Add generated `.h` includes to `main.c` and call each `_Init()` in initialization order.

## Common modules

- `DEBUG_PROTOCOL`: `BOOT_OK`, `key=value`, and event logging helpers.
- `USART`: printf redirection and RX interrupt skeleton.
- `I2C`: software I2C skeleton for display/sensor drivers.
- `SPI`: master transfer skeleton.
- `ADC`, `DAC`, `DMA`, `TIM`, `EXTI`, `CAN`, `GPIO`: common init functions.
