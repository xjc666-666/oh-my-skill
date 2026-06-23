# MSPM0G3519 Workflow

Use this file for normal project creation, project repair, build, flash, and runtime verification work.

## Operating Principles

- Work on the real local project files. Inspect generated `User/config.syscfg`, `User/ti_msp_dl_config.c`, `User/ti_msp_dl_config.h`, `User/main.c`, BSP files, and the Keil `.uvprojx` before claiming success.
- Keep changes scoped. Do not rewrite unrelated user code, delete generated projects, or replace a working `.uvprojx` wholesale unless the user asked for a rebuild.
- Use the bundled scripts first. Patch scripts only when the script is wrong or cannot express the needed operation.
- Use `python {skill_dir}/scripts/dfp_checker.py` early for create, build, flash, and toolchain repair tasks. If it fails, report the missing component and continue only for tasks that do not need that component.

## Normal Create Flow

1. Resolve project name, parent output path, functional requirements, peripheral list, and pin ownership.
2. For every user-wired peripheral except OLED and Keyboard, confirm the actual pins before writing SysConfig.
3. Check toolchain:

```bash
python {skill_dir}/scripts/dfp_checker.py
```

4. Create the project from the bundled skeleton:

```bash
python {skill_dir}/scripts/project_creator.py \
  --name {name} --path {parent_path} --sdk-path {sdk_path}
```

The creator also writes `Project/{name}.uvoptx` with CMSIS-DAP Debug settings and the MSPM0G3519 flash algorithm. Do not ask the user to manually select CMSIS-DAP for newly generated projects unless flashing later fails.

5. Inspect generated project files:

```bash
python {skill_dir}/scripts/syscfg_parser.py \
  --syscfg {project}/User/config.syscfg --list-modules
python {skill_dir}/scripts/syscfg_parser.py \
  --syscfg {project}/User/config.syscfg --list-pins
```

6. Add or modify peripherals through `syscfg_parser.py`; then run conflict checks and generate C code:

```bash
python {skill_dir}/scripts/syscfg_parser.py \
  --syscfg {project}/User/config.syscfg --check-conflicts
python {skill_dir}/scripts/syscfg_generator.py \
  --project-dir {project} --sdk-path {sdk_path}
```

7. Add BSP modules or generate application code only after SysConfig reflects the intended hardware:

```bash
python {skill_dir}/scripts/code_writer.py --project-dir {project} \
  --add-bsp '["UART0","LED"]'
```

8. Validate application code before building:

```bash
python {skill_dir}/scripts/code_checker.py --project-dir {project} --level 3
```

9. Build:

```bash
python {skill_dir}/scripts/keil_builder.py \
  --project {project}/Project/{name}.uvprojx
```

10. Fix build errors in a loop. Use `error_fixer.py` only for known mechanical fixes, then rebuild:

```bash
python {skill_dir}/scripts/error_fixer.py \
  --errors '{json_array}' --project-dir {project} --apply
```

11. Flash only after a successful build. For legacy or externally supplied projects, run the debug configuration helper first:

```bash
python {skill_dir}/scripts/uvprojx_modifier.py debug-config \
  --project {project}/Project/{name}.uvprojx --name {name}
```

## Existing Project Repair Flow

1. Locate the Keil project and infer `{project}` from the `.uvprojx`.
2. Run `syscfg_parser.py --list-modules --list-pins` and inspect `main.c`.
3. If generated config and source disagree, regenerate SysConfig first. Do not patch generated `ti_msp_dl_config.*` by hand except as a temporary diagnostic.
4. Run `code_checker.py --level 3`.
5. Build, parse errors, fix the smallest cause, and rebuild.
6. For runtime failures, add serial `BOOT_OK` or another observable signal before debugging more complex symptoms.

## Completion Criteria

- Project creation: `.uvprojx`, startup, linker/scatter file, include paths, SysConfig output, and smoke build are present.
- Peripheral work: pin assignment has been confirmed or proven fixed by hardware; generated `ti_msp_dl_config.h` matches it.
- Code work: `main.c` implements the requested runtime behavior, not only template/demo code.
- Interrupt work: every DriverLib interrupt enable has the matching `NVIC_EnableIRQ`.
- Build work: `code_checker.py --level 3` and Keil build have passed, or failures are reported with exact remaining errors.
- Flash work: build passed first, CMSIS-DAP Debug settings were generated or verified, and flash success came from backend output.
- Runtime work: serial output, OLED/LED behavior, or another user-requested observable result has been checked.
