# Universal STM32 Skill Improvement Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform stm32-keil from a F103/F407-centric skill into a universal STM32 development platform supporting all 6 families (F103/F407/G4/L4/H7/C0) with unified tooling.

**Architecture:** Extend existing scripts with family-aware abstractions. Each script gets a `FAMILY_CONFIG` dict that maps family → config, replacing hardcoded F103/F407 logic. Data files use a consistent JSON schema across families.

**Tech Stack:** Python 3.10+, PyMuPDF, pyserial, Textual (TUI)

---

## File Structure

### Files to Modify
| File | Change |
|------|--------|
| `chip_db.json` | Fix F411/F429 families, add 20+ chips, DFP version range |
| `scripts/error_fixer.py` | Add G4/L4/H7/C0 header maps and family detection |
| `scripts/pin_conflict_checker.py` | Support all 6 families |
| `scripts/dma_config.py` | Support all 6 families |
| `scripts/clock_config.py` | Add G4/L4/H7/C0 PLL constraints |
| `scripts/pdf_reader.py` | Support all families with graceful fallback |
| `scripts/skeleton_manager.py` | Update for all families |
| `SKILL.md` | Update documentation for universal support |

### Files to Create
| File | Purpose |
|------|---------|
| `data/pin_mapping_g4.json` | STM32G4 pin AF mappings |
| `data/pin_mapping_l4.json` | STM32L4 pin AF mappings |
| `data/pin_mapping_h7.json` | STM32H7 pin AF mappings |
| `data/pin_mapping_c0.json` | STM32C0 pin AF mappings |
| `data/dma_mapping_g4.json` | STM32G4 DMA channel mappings |
| `data/dma_mapping_l4.json` | STM32L4 DMA channel mappings |
| `data/dma_mapping_h7.json` | STM32H7 DMA stream mappings |
| `data/dma_mapping_c0.json` | STM32C0 DMA channel mappings |
| `data/family_config.json` | Unified family configuration |
| `tests/test_error_fixer.py` | Unit tests for error_fixer |
| `tests/test_pin_conflict.py` | Unit tests for pin_conflict_checker |
| `tests/test_clock_config.py` | Unit tests for clock_config |
| `tests/test_dma_config.py` | Unit tests for dma_config |
| `tests/test_chip_db.py` | Unit tests for chip_db consistency |
| `examples/` | Reorganized example projects |

### Files to Move/Delete
| File | Action |
|------|--------|
| `skeleton/stm32f407/实验*` | Move to `examples/stm32f407/` |
| `skeleton/stm32c8t6/` | Merge into `skeleton/f103/` or delete |

---

## Task 1: Create Unified Family Configuration

**Files:**
- Create: `data/family_config.json`

- [ ] **Step 1: Create family_config.json**

This file centralizes all family-specific knowledge that scripts currently hardcode.

```json
{
  "F103": {
    "header_prefix": "stm32f10x",
    "hal_header_prefix": "stm32f1xx_hal",
    "spl_periph_dir": "STM32F10x_StdPeriph_Driver",
    "cmsis_device_dir": "STM32F10x",
    "gpio_clock_bus": "APB2",
    "gpio_mode_prefix": "GPIO_Mode",
    "has_af_mapping": false,
    "default_define": "STM32F10X_MD",
    "sysclk_max": 72000000,
    "pclk1_max": 36000000,
    "pclk2_max": 72000000,
    "pll_type": "F1",
    "reference_manual": "STM32F103_reference_manual.pdf"
  },
  "F407": {
    "header_prefix": "stm32f4xx",
    "hal_header_prefix": "stm32f4xx_hal",
    "spl_periph_dir": "STM32F4xx_StdPeriph_Driver",
    "cmsis_device_dir": "STM32F4xx",
    "gpio_clock_bus": "AHB1",
    "gpio_mode_prefix": "GPIO_Mode",
    "has_af_mapping": true,
    "default_define": "STM32F40_41xxx",
    "sysclk_max": 168000000,
    "pclk1_max": 42000000,
    "pclk2_max": 84000000,
    "pll_type": "F4",
    "reference_manual": "STM32F407_reference_manual.pdf"
  },
  "G4": {
    "header_prefix": "stm32g4xx",
    "hal_header_prefix": "stm32g4xx_hal",
    "spl_periph_dir": null,
    "cmsis_device_dir": "STM32G4xx",
    "gpio_clock_bus": "AHB2",
    "gpio_mode_prefix": "GPIO_MODE",
    "has_af_mapping": true,
    "default_define": "STM32G431xx",
    "sysclk_max": 170000000,
    "pclk1_max": 170000000,
    "pclk2_max": 170000000,
    "pll_type": "G4",
    "hal_only": true,
    "reference_manual": null
  },
  "L4": {
    "header_prefix": "stm32l4xx",
    "hal_header_prefix": "stm32l4xx_hal",
    "spl_periph_dir": null,
    "cmsis_device_dir": "STM32L4xx",
    "gpio_clock_bus": "AHB2",
    "gpio_mode_prefix": "GPIO_MODE",
    "has_af_mapping": true,
    "default_define": "STM32L476xx",
    "sysclk_max": 80000000,
    "pclk1_max": 80000000,
    "pclk2_max": 80000000,
    "pll_type": "L4",
    "hal_only": true,
    "reference_manual": null
  },
  "H7": {
    "header_prefix": "stm32h7xx",
    "hal_header_prefix": "stm32h7xx_hal",
    "spl_periph_dir": null,
    "cmsis_device_dir": "STM32H7xx",
    "gpio_clock_bus": "AHB4",
    "gpio_mode_prefix": "GPIO_MODE",
    "has_af_mapping": true,
    "default_define": "STM32H743xx",
    "sysclk_max": 480000000,
    "pclk1_max": 120000000,
    "pclk2_max": 120000000,
    "pll_type": "H7",
    "hal_only": true,
    "reference_manual": null
  },
  "C0": {
    "header_prefix": "stm32c0xx",
    "hal_header_prefix": "stm32c0xx_hal",
    "spl_periph_dir": null,
    "cmsis_device_dir": "STM32C0xx",
    "gpio_clock_bus": "IOP",
    "gpio_mode_prefix": "GPIO_MODE",
    "has_af_mapping": true,
    "default_define": "STM32C031xx",
    "sysclk_max": 48000000,
    "pclk1_max": 48000000,
    "pclk2_max": 48000000,
    "pll_type": "C0",
    "hal_only": true,
    "reference_manual": null
  }
}
```

- [ ] **Step 2: Verify JSON is valid**

Run: `python -c "import json; json.load(open(r'C:\Users\18158\.claude\skills\stm32-keil\data\family_config.json'))"`
Expected: No output (valid JSON)

---

## Task 2: Fix and Extend chip_db.json

**Files:**
- Modify: `chip_db.json`

- [ ] **Step 1: Fix F411CEU6 family tag**

Change `"family": "F407"` to `"family": "F411"` and add proper family config.

- [ ] **Step 2: Fix F429IGT6 family tag**

Change `"family": "F407"` to `"family": "F429"` and add proper family config.

- [ ] **Step 3: Add missing popular chips**

Add: F103C6T6, F103R8T6, F405RGT6, F407VGT6, F446RET6, G431RBT6, L431RCT6, L452RET6, H743ZIT6, H750VBT6, C011J6

- [ ] **Step 4: Add DFP version range support**

Change `pack_id` from exact version to version range pattern.

- [ ] **Step 5: Validate chip_db.json**

Run: `python -c "import json; db=json.load(open(r'C:\Users\18158\.claude\skills\stm32-keil\chip_db.json')); print(f'{len(db)} chips loaded')"`
Expected: ~25+ chips loaded

---

## Task 3: Extend error_fixer.py for All Families

**Files:**
- Modify: `scripts/error_fixer.py`

- [ ] **Step 1: Add family header maps**

Replace hardcoded F103/F407 logic with family_config-based resolution.

- [ ] **Step 2: Update detect_family()**

Add G4/L4/H7/C0 detection from defines and device names.

- [ ] **Step 3: Update _header_for_periph()**

Use family_config.json for header prefix resolution.

- [ ] **Step 4: Add HAL header support**

Add HAL type mappings (GPIO_InitTypeDef → stm32xxx_hal_gpio.h).

---

## Task 4: Extend pin_conflict_checker.py

**Files:**
- Modify: `scripts/pin_conflict_checker.py`
- Create: `data/pin_mapping_g4.json`
- Create: `data/pin_mapping_l4.json`
- Create: `data/pin_mapping_h7.json`
- Create: `data/pin_mapping_c0.json`

- [ ] **Step 1: Update --family argument**

Change `choices=["F103", "F407"]` to support all families.

- [ ] **Step 2: Create pin mapping JSONs for G4/L4/H7/C0**

Each file follows the same schema as F407: `{pins: {PA0: {functions: [...]}}, jtag_swd_pins: [...]}`.

- [ ] **Step 3: Add graceful fallback**

When pin mapping file is missing, use chip_db to at least validate pin exists on package.

---

## Task 5: Extend dma_config.py

**Files:**
- Modify: `scripts/dma_config.py`
- Create: `data/dma_mapping_g4.json`
- Create: `data/dma_mapping_l4.json`
- Create: `data/dma_mapping_h7.json`
- Create: `data/dma_mapping_c0.json`

- [ ] **Step 1: Update load_dma_mapping()**

Support all families with graceful fallback.

- [ ] **Step 2: Create DMA mapping JSONs**

G4: DMA1/DMA2 with channels (not streams like F4)
L4: DMA1/DMA2 with channels
H7: DMA1/DMA2 with streams (like F4)
C0: DMA1 with channels (simple)

---

## Task 6: Extend clock_config.py

**Files:**
- Modify: `scripts/clock_config.py`

- [ ] **Step 1: Add G4 constraints**

```python
"G4": {
    "sysclk_max": 170_000_000,
    "pclk1_max": 170_000_000,
    "pclk2_max": 170_000_000,
    "pll_vco_in_min": 2_660_000,
    "pll_vco_out_max": 344_000_000,
    ...
}
```

- [ ] **Step 2: Add L4 constraints**

- [ ] **Step 3: Add H7 constraints**

- [ ] **Step 4: Add C0 constraints**

---

## Task 7: Extend pdf_reader.py

**Files:**
- Modify: `scripts/pdf_reader.py`

- [ ] **Step 1: Add graceful fallback for missing PDFs**

When no reference manual exists for a family, return helpful message instead of crashing.

- [ ] **Step 2: Update CLI to accept all families**

---

## Task 8: Clean Up Skeleton Directory

**Files:**
- Move: `skeleton/stm32f407/实验*` → `examples/stm32f407/`
- Remove: `skeleton/stm32c8t6/` (merge into f103 if needed)

- [ ] **Step 1: Create examples/ directory**

- [ ] **Step 2: Move experiment projects**

- [ ] **Step 3: Remove duplicate stm32c8t6/**

- [ ] **Step 4: Update SKILL.md directory structure**

---

## Task 9: Enhance HAL Templates

**Files:**
- Modify: `skeleton/hal_f407/User/main.c`
- Modify: `skeleton/hal_g4/User/main.c`
- Modify: `skeleton/hal_l4/User/main.c`
- Modify: `skeleton/hal_h7/User/main.c`
- Modify: `skeleton/hal_c0/User/main.c`

- [ ] **Step 1: Add peripheral init examples to HAL main.c**

Add commented-out examples for GPIO, USART, TIM, ADC, SPI, I2C.

- [ ] **Step 2: Add SystemClock_Config template**

Each HAL skeleton gets a proper clock config function.

---

## Task 10: Add RTOS Integration

**Files:**
- Create: `skeleton/freertos_f407/` (FreeRTOS template)
- Create: `skeleton/freertos_g4/`
- Create: `skeleton/freertos_h7/`

- [ ] **Step 1: Create FreeRTOS template structure**

- [ ] **Step 2: Add FreeRTOS config template**

- [ ] **Step 3: Add task creation examples**

---

## Task 11: Add Unit Tests

**Files:**
- Create: `tests/test_error_fixer.py`
- Create: `tests/test_pin_conflict.py`
- Create: `tests/test_clock_config.py`
- Create: `tests/test_dma_config.py`
- Create: `tests/test_chip_db.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create test infrastructure**

- [ ] **Step 2: Write chip_db validation tests**

- [ ] **Step 3: Write error_fixer tests**

- [ ] **Step 4: Write pin_conflict_checker tests**

- [ ] **Step 5: Write clock_config tests**

- [ ] **Step 6: Write dma_config tests**

---

## Task 12: Update SKILL.md

**Files:**
- Modify: `SKILL.md`

- [ ] **Step 1: Update supported chips list**

- [ ] **Step 2: Update directory structure**

- [ ] **Step 3: Update family-specific notes**

- [ ] **Step 4: Add RTOS section**

- [ ] **Step 5: Add testing section**

---

## Execution Order

Tasks 1-2: Foundation (family config + chip_db)
Tasks 3-7: Script extensions (can be parallelized)
Task 8: Skeleton cleanup
Tasks 9-10: Template enhancements
Task 11: Tests
Task 12: Documentation

**Estimated total:** ~12 tasks, ~50 steps
