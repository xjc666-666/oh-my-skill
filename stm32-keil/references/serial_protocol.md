# Serial Debug Protocol

Use this protocol whenever the firmware must prove it is running or expose data to the agent.

## Firmware output

Print a boot banner after clocks, GPIO, USART, and board-level init:

```c
DBG_InitBanner("ProjectName", "STM32F407ZGT6");
```

Use machine-readable key-value lines:

```c
DBG_KeyValueU32("tick", tick);
DBG_KeyValueFloat("temp", temp_c);
DBG_Event("adc_ready");
```

Preferred text format:

```text
BOOT_OK project=Name chip=STM32F407ZGT6 boot=1
tick=1234
temp=25.300
event=adc_ready
ERR code=I2C_TIMEOUT bus=1
```

Avoid natural-language-only lines such as `temperature is about 25 degrees`; they are hard to parse.

## Host-side usage

Start/list serial:

```bash
python {skill_dir}/scripts/serial_bridge.py --list
python {skill_dir}/scripts/serial_bridge.py --port COM21 --baud 115200
```

Read and parse:

```bash
python {skill_dir}/scripts/serial_bridge.py --tail 50
python {skill_dir}/scripts/serial_bridge.py --tail 50 --parse
```

Agent API:

```python
from serial_agent import serial_wait_for, serial_parse, serial_send
serial_wait_for("BOOT_OK", timeout=10)
values = serial_parse(50)
serial_send("set kp 1.5")
```

## Debug expectations

- If the user asks to watch data, keep reading until the user says stop.
- If flash succeeds but `BOOT_OK` never appears, treat it as runtime failure, not success.
- For closed-loop tuning, firmware should accept simple ASCII commands and echo applied values.
