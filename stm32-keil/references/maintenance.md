# Maintenance, Versioning, and Self Check

Use these tools when updating the skill itself or validating a fresh install.

## Version metadata

`skill_version.json` is the single place for skill-level version metadata:

- `version`: human-facing skill version.
- `schema`: metadata/cache schema version.
- `capabilities`: short capability identifiers used by maintainers.
- `migrations`: notes for non-destructive upgrade steps.

Do not store generated project state in `skill_version.json`; project state belongs in each project directory.

## Migration

Run the migration helper after pulling/updating the skill:

```bash
python {skill_dir}/scripts/migrate_skill.py
```

Refresh the example index cache:

```bash
python {skill_dir}/scripts/migrate_skill.py --refresh-index
```

The migration helper only touches skill-owned metadata/cache directories. It must not modify user projects.

## Doctor

Run doctor before build/flash work or when the environment looks inconsistent:

```bash
python {skill_dir}/scripts/doctor.py --chip STM32F407ZGT6
python {skill_dir}/scripts/doctor.py --chip STM32F407ZGT6 --json
```

Doctor checks:

- Python version and Python modules from `requirements.txt` scope.
- Keil UV4.
- Required CMSIS/DFP pack for the selected chip.
- CMSIS pack roots.
- STM32CubeMX.
- STM32CubeProgrammer.
- ST-LINK CLI fallback.
- J-Link.
- Optional `pyocd`, `cmake`, `ninja`, `arm-none-eabi-gcc`, `arm-none-eabi-addr2line`, `llvm-addr2line`, and generic `addr2line`.

Keil, the chip DFP, CMSIS pack roots, and Python are required for the normal Keil path. CubeMX, CubeProgrammer, GCC/CMake, J-Link, and PyOCD are optional unless the current workflow needs them.

## Self check without pytest

Use stdlib-only self check for environments that do not have `pytest`:

```bash
python {skill_dir}/scripts/self_check.py
```

This validates JSON metadata, imports core scripts, verifies Flash Download XML injection, and emits a sample peripheral template in a temporary directory.

`pytest` tests may still exist for developer machines, but the skill must not depend on pytest for basic validation.
