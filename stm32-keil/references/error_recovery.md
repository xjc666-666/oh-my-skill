# Error Recovery Loop

Use `scripts/error_recovery.py` to keep build and flash recovery explicit.

## Build loop

Preview fixes:

```bash
python {skill_dir}/scripts/error_recovery.py build-loop --project {uvprojx}
```

Apply known safe fixes after reviewing the diff:

```bash
python {skill_dir}/scripts/error_recovery.py build-loop --project {uvprojx} --apply --max-rounds 3
```

## Classify logs

```bash
python {skill_dir}/scripts/error_recovery.py classify --log {log_file}
```

## Recovery rules

- Missing Flash Algorithm: run `uvprojx_modifier.py flash-config`, then retry Keil flash.
- Missing header: check include path before copying files.
- Undefined symbol: add the source file to `.uvprojx` or fix the function name.
- Wrong family header: do not mix F1 and F4 SPL headers.
- Silent serial after flash: check UART pins/baud and require `DBG_InitBanner()` output.
- HardFault: decode PC/LR with `hardfault_analyzer.py --map ... --elf ...`.

Never keep applying fixes blindly after three unsuccessful rounds. Report the remaining first real error with file/line.
