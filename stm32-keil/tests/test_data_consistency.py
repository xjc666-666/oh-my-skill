"""
Unit tests for stm32-keil skill data consistency.
Run: python -m pytest tests/ -v
"""
import os
import sys
import json
import pytest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
DATA_DIR = SKILL_DIR / "data"

sys.path.insert(0, str(SCRIPTS_DIR))


# ─── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def chip_db():
    with open(SKILL_DIR / "chip_db.json", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def family_config():
    with open(DATA_DIR / "family_config.json", "r", encoding="utf-8") as f:
        return json.load(f)


# ─── chip_db.json tests ───────────────────────────────────────────────

class TestChipDB:
    def test_chip_db_loads(self, chip_db):
        assert isinstance(chip_db, dict)
        assert len(chip_db) >= 20, f"Expected 20+ chips, got {len(chip_db)}"

    def test_all_chips_have_required_fields(self, chip_db):
        required = ["family", "core", "device", "pack_id", "cpu_string",
                     "flash_driver", "svd_file", "defines", "ram_start",
                     "ram_size", "flash_start", "flash_size", "has_fpu",
                     "startup_file", "system_file", "conf_header",
                     "it_header", "it_source", "cmsis_device_dir"]
        for chip_name, chip in chip_db.items():
            for field in required:
                assert field in chip, f"{chip_name} missing field: {field}"

    def test_all_families_valid(self, chip_db, family_config):
        for chip_name, chip in chip_db.items():
            fam = chip["family"]
            assert fam in family_config, \
                f"{chip_name} has family '{fam}' not in family_config.json"

    def test_hal_only_chips_have_hal_fields(self, chip_db):
        for chip_name, chip in chip_db.items():
            if chip.get("hal_only"):
                assert "hal_device_define" in chip or "defines" in chip, \
                    f"{chip_name} is hal_only but missing HAL defines"

    def test_no_duplicate_chip_names(self, chip_db):
        names = list(chip_db.keys())
        assert len(names) == len(set(names)), "Duplicate chip names found"

    def test_flash_ram_sizes_valid(self, chip_db):
        for chip_name, chip in chip_db.items():
            flash_size = int(chip["flash_size"], 16)
            ram_size = int(chip["ram_size"], 16)
            assert flash_size > 0, f"{chip_name} has zero flash"
            assert ram_size > 0, f"{chip_name} has zero RAM"
            assert flash_size <= 0x200000, f"{chip_name} flash too large: {flash_size}"
            assert ram_size <= 0x100000, f"{chip_name} RAM too large: {ram_size}"


# ─── family_config.json tests ─────────────────────────────────────────

class TestFamilyConfig:
    def test_family_config_loads(self, family_config):
        assert isinstance(family_config, dict)
        assert len(family_config) >= 6, f"Expected 6+ families, got {len(family_config)}"

    def test_all_families_have_required_fields(self, family_config):
        required = ["header_prefix", "hal_header_prefix", "gpio_clock_bus",
                     "gpio_clk_enable_macro", "has_af_mapping", "default_define",
                     "sysclk_max", "pclk1_max", "pclk2_max", "pll_type",
                     "conf_header", "it_header", "main_header"]
        for fam, cfg in family_config.items():
            for field in required:
                assert field in cfg, f"Family {fam} missing field: {field}"

    def test_hal_only_families_flagged(self, family_config):
        hal_only_expected = {"G4", "L4", "H7", "C0"}
        for fam in hal_only_expected:
            assert fam in family_config, f"Missing family: {fam}"
            assert family_config[fam].get("hal_only") is True, \
                f"Family {fam} should be hal_only"

    def test_spl_families_not_hal_only(self, family_config):
        spl_families = {"F103", "F407", "F411", "F429"}
        for fam in spl_families:
            if fam in family_config:
                assert not family_config[fam].get("hal_only", False), \
                    f"Family {fam} should not be hal_only"


# ─── Pin mapping tests ───────────────────────────────────────────────

class TestPinMappings:
    @pytest.mark.parametrize("family", ["f103", "f407", "g4", "l4", "h7", "c0"])
    def test_pin_mapping_exists(self, family):
        path = DATA_DIR / f"pin_mapping_{family}.json"
        assert path.exists(), f"Missing pin mapping: {path}"

    @pytest.mark.parametrize("family", ["f103", "f407", "g4", "l4", "h7", "c0"])
    def test_pin_mapping_loads(self, family):
        path = DATA_DIR / f"pin_mapping_{family}.json"
        if not path.exists():
            pytest.skip(f"Pin mapping not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "pins" in data, f"pin_mapping_{family}.json missing 'pins' key"
        assert len(data["pins"]) > 0, f"pin_mapping_{family}.json has no pins"


# ─── DMA mapping tests ───────────────────────────────────────────────

class TestDMAMappings:
    @pytest.mark.parametrize("family", ["f103", "f407", "g4", "l4", "h7", "c0"])
    def test_dma_mapping_exists(self, family):
        path = DATA_DIR / f"dma_mapping_{family}.json"
        assert path.exists(), f"Missing DMA mapping: {path}"

    @pytest.mark.parametrize("family", ["f103", "f407", "g4", "l4", "h7", "c0"])
    def test_dma_mapping_loads(self, family):
        path = DATA_DIR / f"dma_mapping_{family}.json"
        if not path.exists():
            pytest.skip(f"DMA mapping not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "mappings" in data, f"dma_mapping_{family}.json missing 'mappings' key"
        assert len(data["mappings"]) > 0, f"dma_mapping_{family}.json has no mappings"


# ─── Script import tests ─────────────────────────────────────────────

class TestScriptImports:
    def test_import_utils(self):
        from utils import load_chip_db, load_family_config, get_chip_family
        assert callable(load_chip_db)
        assert callable(load_family_config)
        assert callable(get_chip_family)

    def test_import_error_fixer(self):
        from error_fixer import detect_family, analyze_and_fix
        assert callable(detect_family)
        assert callable(analyze_and_fix)

    def test_import_pin_conflict(self):
        from pin_conflict_checker import check_pin_conflicts, load_pin_mapping
        assert callable(check_pin_conflicts)
        assert callable(load_pin_mapping)

    def test_import_dma_config(self):
        from dma_config import get_dma_options, load_dma_mapping
        assert callable(get_dma_options)
        assert callable(load_dma_mapping)

    def test_import_clock_config(self):
        from clock_config import calculate
        assert callable(calculate)


# ─── Error patterns tests ────────────────────────────────────────────

class TestErrorPatterns:
    def test_error_patterns_loads(self):
        path = SKILL_DIR / "references" / "error_patterns.json"
        assert path.exists(), "Missing error_patterns.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "patterns" in data
        assert len(data["patterns"]) >= 10

    def test_all_patterns_have_required_fields(self):
        path = SKILL_DIR / "references" / "error_patterns.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for pat in data["patterns"]:
            assert "id" in pat, f"Pattern missing 'id'"
            assert "regex" in pat, f"Pattern {pat.get('id')} missing 'regex'"
            assert "confidence" in pat, f"Pattern {pat.get('id')} missing 'confidence'"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
