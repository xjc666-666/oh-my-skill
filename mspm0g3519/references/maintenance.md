# Skill Maintenance

Use this file when updating this skill, its scripts, or its bundled references.

## Keep the Entry Point Light

- Keep `SKILL.md` focused on trigger description, reference routing, mandatory rules, quick commands, and completion criteria.
- Move detailed hardware, SysConfig, code, debug, and maintenance notes into `references/*.md`.
- Avoid duplicating the same rule in many files. If duplication is necessary, keep JSON resources as the structured source of truth.

## Baseline Validation

Run the offline self-check after edits:

```bash
python {skill_dir}/scripts/self_check.py
```

This validates:

- required files
- `SKILL.md` frontmatter
- JSON resources
- Python script compilation
- CLI `--help` behavior for scripts

For machine-readable output:

```bash
python {skill_dir}/scripts/self_check.py --json
```

## Additional Checks

Run these when touching related areas:

```bash
python -m compileall -q {skill_dir}/scripts
python {skill_dir}/scripts/dfp_checker.py --help
python {skill_dir}/scripts/hardfault_analyzer.py --gen-handler
python {skill_dir}/scripts/syscfg_parser.py --help
```

When toolchain and hardware are available, also create a disposable smoke project, run SysConfig generation, build, and verify that `.hex` and `.axf` are emitted.

## Packaging Hygiene

- Do not depend on `__pycache__` or local build artifacts.
- Do not assume a specific user name or absolute project path.
- Keep SDK/SysConfig paths configurable through `references/sdk_paths.json`, environment variables, or explicit CLI arguments.
- Preserve compatibility with Windows PowerShell, Keil MDK-ARM, and TI SysConfig paths containing spaces.
