# Debug and Runtime Verification

Use this file for build failures, flashing, serial checks, HardFault work, and proving firmware is actually running.

## Build

```bash
python {skill_dir}/scripts/keil_builder.py \
  --project {project}/Project/{name}.uvprojx
```

Review:

- return success or failure
- parsed errors and warnings
- `Project/build_output.txt`
- Flash/RAM size output
- generated `.hex` and `.axf` location

If build fails, fix the root cause and rebuild. Use `error_fixer.py` for known safe mechanical fixes:

```bash
python {skill_dir}/scripts/error_fixer.py \
  --errors '{json_array}' --project-dir {project} --apply
```

Stop after repeated failures and report the exact remaining compiler/linker diagnostics.

## Flash

Flash only after build passes.

New projects created by `project_creator.py` are preconfigured with CMSIS-DAP Debug settings in `Project/{name}.uvoptx`. For legacy or externally supplied projects, run:

```bash
python {skill_dir}/scripts/uvprojx_modifier.py debug-config \
  --project {project}/Project/{name}.uvprojx --name {name}
```

Then flash:

```bash
python {skill_dir}/scripts/flasher.py \
  --project {project}/Project/{name}.uvprojx
```

If `uv4 -f` reports Target DLL cancelled or no flash algorithm:

1. Re-run `uvprojx_modifier.py debug-config` and confirm `Project/{name}.uvoptx` contains `BIN\CMSIS_AGDI.dll`.
2. Verify Keil DFP and the `MSPM0GX51X_MAIN_512KB.FLM` flash algorithm are installed.
3. If it still fails, have the user select CMSIS-DAP in Keil, enable Reset and Run in the Flash Download tab, press OK, and retry command-line flash after Keil stores the setting.

## Serial Runtime Checks

List serial ports:

```bash
python {skill_dir}/scripts/serial_bridge.py --list
```

Start or query serial bridge:

```bash
python {skill_dir}/scripts/serial_bridge.py --port COMx --baud 115200 --start
python {skill_dir}/scripts/serial_bridge.py --tail 30 --parse
python {skill_dir}/scripts/serial_bridge.py --send "AT+VALUE=100"
```

For firmware that must prove it booted, add a parseable line after init:

```text
BOOT_OK project=Name chip=MSPM0G3519 boot=1
```

## HardFault

Cortex-M0+ has limited fault status compared with Cortex-M3/M4. Prefer stack-frame PC/LR/xPSR analysis; do not rely on CFSR/HFSR being present.

Generate a compatible handler template:

```bash
python {skill_dir}/scripts/hardfault_analyzer.py --gen-handler
```

Analyze a captured register dump:

```bash
python {skill_dir}/scripts/hardfault_analyzer.py \
  --registers '{"PC":"0x00001234","LR":"0x00005678","xPSR":"0x01000003"}' \
  --map {project}/Project/Listings/{name}.map
```

Watch serial for dumps:

```bash
python {skill_dir}/scripts/hardfault_watcher.py \
  --port COMx --baud 115200 \
  --map {project}/Project/Listings/{name}.map
```

MSPM0G3519 executable flash ranges are `0x00000000-0x0007FFFF` and `0x00400000-0x0047FFFF`. Do not apply STM32-style `0x08000000` assumptions.

## Runtime Completion

Use at least one concrete observable signal:

- serial `BOOT_OK` or requested telemetry
- OLED content with correct page and column bounds
- LED/PWM visible behavior
- ADC/DAC reading or measured voltage
- flash backend success plus reset-and-run evidence
