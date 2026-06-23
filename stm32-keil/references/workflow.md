# STM32 Keil Workflow

Use this workflow for every `/stm32-keil` project.

## Required order

1. Resolve chip, family, library style, project name, target directory, and functional requirements.
2. Run environment checks early when build/flash is requested:
   `python {skill_dir}/scripts/doctor.py --chip {chip}`
3. Create the project:
   `python {skill_dir}/scripts/project_creator.py --chip {chip} --name {name} --path {path} --library {SPL|HAL} --smoke-build`
4. Search examples before writing peripheral code:
   `python {skill_dir}/scripts/example_indexer.py --peripheral USART --family F407`
5. Confirm module wiring/pins with the user before writing hardware-specific code.
6. Emit reusable driver skeletons where possible:
   `python {skill_dir}/scripts/peripheral_templates.py --project {project_root} --uvprojx {uvprojx} --peripheral USART --family F407`
7. Write real application logic in `main.c`; never stop at an empty `while(1)`.
8. Build and recover:
   `python {skill_dir}/scripts/error_recovery.py build-loop --project {uvprojx}`
   Use `--apply` only after reviewing the proposed diff.
9. Flash:
   `python {skill_dir}/scripts/flasher.py --project {uvprojx} --backend keil`
10. If serial output is expected, require the firmware to print `BOOT_OK` and parse key-value telemetry with `serial_bridge.py` or `serial_agent.py`.

## Library policy

- F103/F407 default to SPL unless the user requests HAL.
- G4/L4/H7/C0 use HAL.
- Use CubeMX only when the user asks for CubeMX/HAL configuration, or when no skeleton can cover the chip.

## Quality gates

- `.uvprojx` and `.uvoptx` must use relative source paths.
- Keil Flash Download Algorithm must be present for both `UL2CM3` and `ST-LINKIII-KEIL_SWO`.
- New `.c` files must be added to the Keil project.
- Generated code must compile before reporting completion.
- A flashed project is not considered validated unless Keil reports success or another backend reports verified programming.
