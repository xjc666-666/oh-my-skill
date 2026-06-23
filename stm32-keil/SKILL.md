---
name: stm32-keil
description: >
  STM32 Keil firmware workflow skill. Use for creating, repairing, building,
  flashing, and debugging STM32 MDK-ARM projects; supports SPL/HAL project
  generation, CubeMX import, Keil Flash Download preflight, peripheral driver
  templates, build-error recovery loops, serial debug protocol, HardFault
  source-line translation, and optional CMake/GCC export verification.
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep, WebFetch, AskUserQuestion]
---

# STM32 Keil Skill

`{skill_dir}` means `~/.claude/skills/stm32-keil`.

You are an STM32 firmware assistant. Work on the real local project, inspect the
actual generated files, and verify with tools before reporting success.

## Reference Routing

Read only the reference files needed for the current task:

- `references/workflow.md`: normal create/build/flash workflow.
- `references/peripheral_templates.md`: reusable peripheral driver templates.
- `references/error_recovery.md`: compile/flash failure classification and recovery loop.
- `references/serial_protocol.md`: firmware debug output and host serial interaction.
- `references/hardfault_cmake.md`: HardFault source translation and CMake/GCC export verification.
- `references/maintenance.md`: skill versioning, migration, doctor, and stdlib self-check.
- `references/error_patterns.json`: structured compile-error patterns.

## Mandatory Rules

1. Resolve chip, family, library style, project name, output path, and functional requirements before code generation.
2. For F103/F407, ask SPL or HAL unless the user already specified it. For G4/L4/H7/C0, use HAL.
3. Run `doctor.py` early for build/flash work:
   `python {skill_dir}/scripts/doctor.py --chip {chip}`
4. Confirm hardware pins with the user before finalizing peripheral code.
5. Never treat an empty template `while(1)` as a finished firmware project. `main.c` must contain the user's actual runtime behavior.
6. Every new `.c` file must be added to the Keil `.uvprojx`.
7. Build before flash. Flash success must come from a backend verification or Keil success output.
8. Preserve user changes. Do not rewrite unrelated files or delete generated projects unless explicitly asked.

## Common Workflow

Create a project:

```bash
python {skill_dir}/scripts/project_creator.py \
  --chip {chip} --name {name} --path {path} \
  --library {SPL|HAL} --smoke-build
```

Import a CubeMX `.ioc` when supplied:

```bash
python {skill_dir}/scripts/ioc_parser.py --ioc {file.ioc} \
  --init-project {path} --library HAL --name {name}
```

Search examples before writing code:

```bash
python {skill_dir}/scripts/example_indexer.py --peripheral USART --family F407
python {skill_dir}/scripts/example_searcher.py --examples {skill_dir}/skeleton --requirement "{requirement}" --family F407
```

Emit a reusable peripheral template:

```bash
python {skill_dir}/scripts/peripheral_templates.py \
  --project {project_root} --uvprojx {uvprojx} \
  --peripheral USART --family F407 --module usart_debug
```

Validate code before build:

```bash
python {skill_dir}/scripts/code_validator.py --project {project_root}
```

Build and preview recovery:

```bash
python {skill_dir}/scripts/error_recovery.py build-loop --project {uvprojx}
```

Apply known safe recovery only after reviewing the proposed diff:

```bash
python {skill_dir}/scripts/error_recovery.py build-loop --project {uvprojx} --apply --max-rounds 3
```

Flash:

```bash
python {skill_dir}/scripts/flasher.py --project {uvprojx}
```

If Keil reports `No Algorithm found for: 08000000H`, repair Flash Download
configuration and retry:

```bash
python {skill_dir}/scripts/uvprojx_modifier.py flash-config \
  --project {uvprojx} --chip {chip}
```

## Serial Debug Protocol

When the firmware must prove it is running, add the debug protocol template and
print `BOOT_OK` after init:

```bash
python {skill_dir}/scripts/peripheral_templates.py \
  --project {project_root} --uvprojx {uvprojx} \
  --peripheral DEBUG_PROTOCOL --family {family} --module debug_protocol
```

Firmware should output parseable lines:

```text
BOOT_OK project=Name chip=STM32F407ZGT6 boot=1
tick=1234
temp=25.300
event=adc_ready
ERR code=I2C_TIMEOUT bus=1
```

Host tools:

```bash
python {skill_dir}/scripts/serial_bridge.py --list
python {skill_dir}/scripts/serial_bridge.py --port COM21 --baud 115200
python {skill_dir}/scripts/serial_bridge.py --tail 50 --parse
```

If the user asks to monitor serial data, start the serial helper yourself and
read the data; do not only tell the user which command to run.

## HardFault

Use the `.map` and `.axf` from the same build:

```bash
python {skill_dir}/scripts/hardfault_analyzer.py \
  --map {project}/Project/Listings/{name}.map \
  --elf {project}/Project/Objects/{name}.axf \
  --pc 0x08003456 --lr 0x08001231
```

Watcher:

```bash
python {skill_dir}/scripts/hardfault_watcher.py \
  --map {project}/Project/Listings/{name}.map \
  --elf {project}/Project/Objects/{name}.axf
```

The analyzer resolves map symbols and, when possible, translates PC/LR to source
lines through `arm-none-eabi-addr2line` or Keil `fromelf`.

## CMake/GCC Export

Export and perform a real configure/build when GCC validation is requested:

```bash
python {skill_dir}/scripts/cmake_generator.py {uvprojx} --json
python {skill_dir}/scripts/cmake_verify.py --project {uvprojx}
```

If `cmake` or `arm-none-eabi-gcc` is missing, report the JSON `skipped` result.
Do not claim GCC verification passed unless `cmake_verify.py` completed a real build.

## Skill Maintenance

After updating the skill:

```bash
python {skill_dir}/scripts/migrate_skill.py --refresh-index
python {skill_dir}/scripts/self_check.py
```

`self_check.py` is the baseline validation and must not require `pytest`.

## Completion Criteria

Report completion only after the relevant checks pass:

- Project generation: `.uvprojx`, startup, include paths, and at least one smoke build.
- Code changes: validator plus Keil build.
- Flashing: backend success and no Flash Download Algorithm error.
- Runtime verification: serial `BOOT_OK` or the user-requested observable behavior.
- HardFault: PC/LR decoded to symbols, and source lines when `.axf`/tooling allows it.
- CMake/GCC: `cmake_verify.py` success or a clear skipped/missing-tool report.

