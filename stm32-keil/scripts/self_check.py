"""
Standard-library self-check for stm32-keil.

This is intentionally independent of pytest so users can validate a fresh
skill install with only Python.
"""
import importlib
import json
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def _ok(name: str, detail: str = "") -> dict:
    return {"name": name, "ok": True, "detail": detail}


def _fail(name: str, detail: str) -> dict:
    return {"name": name, "ok": False, "detail": detail}


def _check_json(rel: str, min_items: int = 1) -> dict:
    try:
        data = json.loads((SKILL_DIR / rel).read_text(encoding="utf-8"))
        size = len(data) if hasattr(data, "__len__") else 1
        if size < min_items:
            return _fail(f"json:{rel}", f"too small: {size}")
        return _ok(f"json:{rel}", f"{type(data).__name__} size={size}")
    except Exception as exc:
        return _fail(f"json:{rel}", str(exc))


def _check_import(module: str) -> dict:
    try:
        importlib.import_module(module)
        return _ok(f"import:{module}")
    except Exception as exc:
        return _fail(f"import:{module}", str(exc))


def _check_flash_config() -> dict:
    try:
        from uvprojx_modifier import ensure_flash_download_config
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            uvprojx = root / "T.uvprojx"
            uvoptx = root / "T.uvoptx"
            uvprojx.write_text(
                '<Project><Targets><Target><TargetOption><TargetCommonOption>'
                '<Device>STM32F407ZGTx</Device><FlashDriverDll />'
                '</TargetCommonOption></TargetOption></Target></Targets></Project>',
                encoding="utf-8",
            )
            uvoptx.write_text(
                '<ProjectOpt><Target><TargetOption><TargetDriverDllRegistry>'
                '<SetRegEntry><Key>ST-LINKIII-KEIL_SWO</Key><Name /></SetRegEntry>'
                '</TargetDriverDllRegistry></TargetOption></Target></ProjectOpt>',
                encoding="utf-8",
            )
            ensure_flash_download_config(str(uvprojx), "STM32F407ZGT6")
            text = uvoptx.read_text(encoding="utf-8")
            if "-FF0STM32F4xx_1024" not in text or "-R1" not in text:
                return _fail("flash-config", "algorithm flags missing")
        return _ok("flash-config")
    except Exception as exc:
        return _fail("flash-config", str(exc))


def _check_template_emit() -> dict:
    try:
        from peripheral_templates import emit_template
        with tempfile.TemporaryDirectory() as td:
            result = emit_template(td, "DEBUG_PROTOCOL", "F407", "debug_protocol")
            if not Path(result["source"]).is_file() or not Path(result["header"]).is_file():
                return _fail("peripheral-template", "files not emitted")
        return _ok("peripheral-template")
    except Exception as exc:
        return _fail("peripheral-template", str(exc))


def run() -> dict:
    checks = [
        _check_json("chip_db.json", 10),
        _check_json("data/family_config.json", 4),
        _check_json("references/error_patterns.json", 1),
        _check_json("skill_version.json", 1),
    ]
    for module in [
        "utils", "project_creator", "uvprojx_modifier", "keil_builder",
        "flasher", "example_indexer", "peripheral_templates",
        "error_recovery", "hardfault_analyzer", "cmake_generator",
        "cmake_verify", "doctor", "migrate_skill",
    ]:
        checks.append(_check_import(module))
    checks.append(_check_flash_config())
    checks.append(_check_template_emit())
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


def main() -> int:
    report = run()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
