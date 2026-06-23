# HardFault Source Translation and CMake/GCC Verification

Use this reference for runtime crashes and cross-toolchain export checks.

## HardFault input format

Firmware should print at least PC and LR. Prefer also R0-R3, R12, xPSR, CFSR, and HFSR:

```text
HardFault
R0=0x00000000 R1=0x20001000 R2=0x00000004 R3=0x00000000
R12=0x00000000 LR=0x08001231 PC=0x08003456 xPSR=0x21000000
CFSR=0x00008200 HFSR=0x40000000
```

Keep the `.map` and `.axf` from the same build. Mixed artifacts produce misleading source lines.

## Manual analysis

```bash
python {skill_dir}/scripts/hardfault_analyzer.py \
  --map {project}/Project/Listings/{name}.map \
  --elf {project}/Project/Objects/{name}.axf \
  --pc 0x08003456 --lr 0x08001231
```

The analyzer first resolves symbols from the Keil `.map` file. If `--elf` is supplied, it also tries:

1. `arm-none-eabi-addr2line` from PATH.
2. `llvm-addr2line` or generic `addr2line` from PATH.
3. Keil `fromelf.exe` from ARMCC/ARMCLANG.
4. `fromelf` from PATH.

Report both the symbol and the translated source line when available.

## Watcher

```bash
python {skill_dir}/scripts/hardfault_watcher.py \
  --map {project}/Project/Listings/{name}.map \
  --elf {project}/Project/Objects/{name}.axf
```

Use watcher when serial logs contain HardFault dumps. If serial is silent, debug startup, clock, UART, and reset behavior before assuming HardFault.

## CMake/GCC export

Generate CMake/GCC files from the Keil project:

```bash
python {skill_dir}/scripts/cmake_generator.py {project}/Project/{name}.uvprojx --json
```

This writes:

- `{project}/Project/CMakeLists.txt`
- `{project}/Project/gcc_linker.ld`

The generator reads Keil sources, include paths, defines, target CPU, and memory regions from `.uvprojx`.

## Real build verification

Run a configure/build after export:

```bash
python {skill_dir}/scripts/cmake_verify.py \
  --project {project}/Project/{name}.uvprojx \
  --build-dir {project}/Project/build-gcc
```

The verifier requires `cmake` and `arm-none-eabi-gcc`. If either is missing, it returns a JSON `skipped: true` result rather than pretending the export passed.

Treat a GCC build failure as useful signal. Common causes:

- ARMCC assembly startup files are not GCC-compatible.
- Keil-specific pragmas or scatter-loading symbols need portable guards.
- Include paths in the Keil project point to machine-local absolute directories.
- Linker memory differs from the chip database or Keil target settings.

Do not report CMake/GCC export as verified unless `cmake_verify.py` completed a real build or clearly reported that the toolchain was unavailable.
