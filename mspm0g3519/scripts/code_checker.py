"""
Three-level code quality checker for MSPM0G3519 project code.
Level 1: Syntax checks (brackets, semicolons, strings, macros)
Level 2: Logic checks (uninitialized variables, type issues, dead code)
Level 3: Platform checks (GPIO pins, clock order, NVIC, SYSCFG_DL_init)
"""
import os
import sys
import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

SCRIPT_DIR = str(Path(__file__).resolve().parent)
SKILL_DIR = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, SCRIPT_DIR)
from utils import normalize_path, load_hardware_pin_map


def check_project(project_dir: str, level: int = 3) -> Dict:
    """Run code quality checks on the project. Returns issues and auto-fixes."""

    # Find all C source files
    c_files = _find_c_files(project_dir)
    issues = []
    fixes = []

    for fpath in c_files:
        # Level 1: Syntax
        if level >= 1:
            s_issues, s_fixes = _check_syntax(fpath)
            issues.extend(s_issues)
            fixes.extend(s_fixes)

        # Level 2: Logic
        if level >= 2:
            l_issues, l_fixes = _check_logic(fpath)
            issues.extend(l_issues)
            fixes.extend(l_fixes)

    # Level 3: Platform (whole-project checks)
    if level >= 3:
        p_issues, p_fixes = _check_platform(project_dir, c_files)
        issues.extend(p_issues)
        fixes.extend(p_fixes)

    auto_fixable = [f for f in fixes if f.get("auto_fixable")]
    manual = [f for f in fixes if not f.get("auto_fixable")]

    return {
        "total_issues": len(issues),
        "level1_syntax": len([i for i in issues if i["level"] == 1]),
        "level2_logic": len([i for i in issues if i["level"] == 2]),
        "level3_platform": len([i for i in issues if i["level"] == 3]),
        "issues": issues,
        "auto_fixable": len(auto_fixable),
        "manual_review": len(manual),
        "fixes": fixes,
    }


def _find_c_files(project_dir: str) -> List[str]:
    """Find all .c source files in project."""
    c_files = []
    for root, dirs, files in os.walk(project_dir):
        # Skip Output/, Source/ti/ (DriverLib is correct by definition), third_party
        if any(skip in root for skip in ["Output", "Source\\ti", "third_party", ".git"]):
            continue
        for f in files:
            if f.endswith(".c"):
                c_files.append(os.path.join(root, f))
    return c_files


def _strip_multiline_comments(text: str) -> str:
    def replacer(match):
        s = match.group(0)
        return "".join('\n' if c == '\n' else ' ' for c in s)
    return re.sub(r'/\*.*?\*/', replacer, text, flags=re.DOTALL)


def _check_syntax(filepath: str) -> Tuple[List[Dict], List[Dict]]:
    """Level 1: Syntax checks."""
    issues = []
    fixes = []

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return [], []

    content_clean = _strip_multiline_comments(content)
    lines = content_clean.split("\n")
    fname = os.path.basename(filepath)

    # Check bracket matching: { }, ( ), [ ]
    for pair_str, open_char, close_char in [
        ("braces", "{", "}"), ("parens", "(", ")"), ("brackets", "[", "]")
    ]:
        count = 0
        for lnum, line in enumerate(lines, 1):
            # Skip comments and strings (simplified)
            clean = _strip_comments_and_strings(line)
            count += clean.count(open_char) - clean.count(close_char)
        if count != 0:
            issues.append({
                "level": 1, "file": fname, "line": 0,
                "type": f"unbalanced_{pair_str}",
                "message": f"Unbalanced {pair_str}: {count} extra {'open' if count > 0 else 'close'}",
            })

    # Check #if / #ifdef / #ifndef / #endif pairing
    if_count = 0
    for lnum, line in enumerate(lines, 1):
        if re.match(r'^\s*#\s*if', line):
            if_count += 1
        elif re.match(r'^\s*#\s*endif', line):
            if_count -= 1
    if if_count != 0:
        issues.append({
            "level": 1, "file": fname, "line": 0,
            "type": "unbalanced_ifdef",
            "message": f"Unbalanced #if/#endif: {if_count} unmatched",
        })

    # Check for non-existent #include files
    for lnum, line in enumerate(lines, 1):
        m = re.match(r'^\s*#include\s+"([^"]+)"', line)
        if m:
            inc_path = m.group(1)
            proj_dir = _project_root_from_file(filepath)
            found = _include_exists(proj_dir, filepath, inc_path)
            if not found:
                issues.append({
                    "level": 1, "file": fname, "line": lnum,
                    "type": "missing_include",
                    "message": f"#include \"{inc_path}\" file not found in project",
                })

    # Check for empty while(1) in main.c
    if fname == "main.c":
        if re.search(r'while\s*\(\s*1\s*\)\s*\{\s*\}', content):
            issues.append({
                "level": 1, "file": fname, "line": 0,
                "type": "empty_while1",
                "message": "while(1) body is empty - must contain actual logic",
            })

    return issues, fixes


def _check_logic(filepath: str) -> Tuple[List[Dict], List[Dict]]:
    """Level 2: Logic checks."""
    issues = []
    fixes = []

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return [], []

    lines = content.split("\n")
    fname = os.path.basename(filepath)

    # Check for potential uninitialized variable usage
    # Simple heuristic: local variable declared without init, then used in if/while condition
    # Pattern: "type name;" followed later by "name" used in comparison
    decls = re.findall(r'^\s*(?:uint\w+_t|int\w+_t|char|float|double)\s+(\w+)\s*;', content, re.MULTILINE)
    for var in decls:
        # Check if this variable is used in any expression
        uses = re.findall(rf'(?<!\w){re.escape(var)}(?!\w)', content)
        if len(uses) > 1:  # More than just the declaration
            # Check if there's an assignment between decl and first use
            decl_pos = content.find(f"{var};")
            if decl_pos >= 0:
                post_decl = content[decl_pos:]
                first_use = 999999
                for m in re.finditer(rf'(?<!\w){re.escape(var)}(?!\w)\s*[=]', post_decl):
                    pass  # Assigned somehow
                if not re.search(rf'{re.escape(var)}\s*=', post_decl[:500]):
                    issues.append({
                        "level": 2, "file": fname, "line": 0,
                        "type": "possibly_uninitialized",
                        "message": f"Variable '{var}' may be used before initialization",
                    })

    # Check for dead code after return/break/continue
    for lnum, line in enumerate(lines, 1):
        stripped = line.strip()
        if "}" in stripped:
            continue
        if stripped == "return;" or re.match(r'^return\s+', stripped):
            # Check next non-blank line
            for j in range(lnum, min(lnum + 5, len(lines))):
                next_line = lines[j].strip()
                if next_line == "}":
                    break
                if next_line and not next_line.startswith("//") and next_line != "}":
                    if not re.match(r'^(case\s|default\s*:|label:)', next_line):
                        issues.append({
                            "level": 2, "file": fname, "line": lnum + 1,
                            "type": "dead_code",
                            "message": f"Code after return/break/continue on line {lnum} may be unreachable",
                        })
                    break

    # Check for type truncation: uint8_t x = some_function_returning_uint32();
    truncations = re.findall(
        r'uint(?:8|16)_t\s+(\w+)\s*=\s*(\w+)\s*\(',
        content
    )
    for var, func in truncations:
        if re.search(rf'\buint(?:8|16)_t\s+{re.escape(func)}\s*\(', content):
            continue
        issues.append({
            "level": 2, "file": fname, "line": 0,
            "type": "possible_truncation",
            "message": f"Variable '{var}' (8/16-bit) assigned from '{func}()' may truncate",
        })

    return issues, fixes


def _check_platform(project_dir: str, c_files: List[str]) -> Tuple[List[Dict], List[Dict]]:
    """Level 3: Platform-specific checks for MSPM0G3519."""
    issues = []
    fixes = []

    hw = load_hardware_pin_map()
    reserved = hw.get("reserved_pins", [])
    all_content = ""

    # Collect all source content
    for fpath in c_files:
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                all_content += f.read() + "\n"
        except Exception:
            pass

    # Check SYSCFG_DL_init is called exactly once
    init_count = all_content.count("SYSCFG_DL_init()")
    if init_count == 0:
        issues.append({
            "level": 3, "file": "main.c", "line": 0,
            "type": "missing_syscfg_init",
            "message": "SYSCFG_DL_init() not called - required for peripheral initialization",
        })
    elif init_count > 1:
        issues.append({
            "level": 3, "file": "main.c", "line": 0,
            "type": "multiple_syscfg_init",
            "message": f"SYSCFG_DL_init() called {init_count} times - should only be called once",
        })

    # Check that SYSCFG_DL_init is called first in main()
    main_path = os.path.join(project_dir, "User", "main.c")
    if os.path.isfile(main_path):
        try:
            with open(main_path, "r", encoding="utf-8") as f:
                main_content = f.read()
            main_lines = main_content.split("\n")
            in_main = False
            brace_count = 0
            for lnum, line in enumerate(main_lines, 1):
                if "int main" in line:
                    in_main = True
                    continue
                if in_main and "{" in line:
                    brace_count += line.count("{")
                    continue
                if in_main and brace_count > 0:
                    stripped = line.strip()
                    if stripped and not stripped.startswith("//"):
                        if "SYSCFG_DL_init()" not in stripped:
                            issues.append({
                                "level": 3, "file": "main.c", "line": lnum,
                                "type": "init_order",
                                "message": "SYSCFG_DL_init() should be called first in main()",
                            })
                        break
        except Exception:
            pass

    # Check GPIO pin validity (extract pin string references from code)
    pin_refs = re.findall(r'"(P[A-C]\d+)"', all_content)
    for pin in pin_refs:
        if pin in reserved:
            issues.append({
                "level": 3, "file": "main.c", "line": 0,
                "type": "reserved_pin_usage",
                "message": f"Pin {pin} is hardware-reserved: {hw.get('reserved_pins_reason', {}).get(pin, 'fixed')}",
            })

    # Check NVIC enable paired with DL interrupt enable (bidirectional)
    dl_int_enables = re.findall(r'DL_(\w+)_enableInterrupt\(', all_content)
    nvic_enables = re.findall(r'NVIC_EnableIRQ\((\w+)\)', all_content)
    if dl_int_enables and not nvic_enables:
        issues.append({
            "level": 3, "file": "main.c", "line": 0,
            "type": "missing_nvic_for_dl_int",
            "message": "DL interrupt enabled but no NVIC_EnableIRQ() found. Interrupts will not fire.",
        })
    if nvic_enables and not dl_int_enables:
        issues.append({
            "level": 3, "file": "main.c", "line": 0,
            "type": "missing_dl_int_for_nvic",
            "message": "NVIC_EnableIRQ() found but no DL_xxx_enableInterrupt() - peripheral IMASK may not be set. Interrupts will not fire.",
        })

    # Check every ISR handler has both peripheral + NVIC interrupt enabled
    isr_funcs = re.findall(r'void\s+(\w+_INST_IRQHandler)\s*\(', all_content)
    for isr_name in isr_funcs:
        # Extract prefix, e.g. "ADC0" from "ADC0_INST_IRQHandler"
        prefix_match = re.match(r'(\w+)_INST_IRQHandler', isr_name)
        if prefix_match:
            prefix = prefix_match.group(1)
            # Check DL peripheral interrupt enable for this peripheral
            dl_enabled = bool(re.search(rf'DL_\w+_enableInterrupt\(\s*{prefix}_INST', all_content))
            # Check NVIC enable
            nvic_enabled = bool(re.search(rf'NVIC_EnableIRQ\(\s*{prefix}_INST_INT_IRQN', all_content))
            if not dl_enabled and not nvic_enabled:
                issues.append({
                    "level": 3, "file": "main.c", "line": 0,
                    "type": "isr_no_interrupt",
                    "message": f"ISR '{isr_name}' defined but no DL_xxx_enableInterrupt() or NVIC_EnableIRQ() found for {prefix}",
                })
            elif not dl_enabled:
                issues.append({
                    "level": 3, "file": "main.c", "line": 0,
                    "type": "isr_missing_peripheral_int",
                    "message": f"ISR '{isr_name}' defined but no DL_xxx_enableInterrupt({prefix}_INST, ...) - peripheral IMASK not set",
                })
            elif not nvic_enabled:
                issues.append({
                    "level": 3, "file": "main.c", "line": 0,
                    "type": "isr_missing_nvic",
                    "message": f"ISR '{isr_name}' defined but no NVIC_EnableIRQ({prefix}_INST_INT_IRQN) - NVIC not enabled",
                })

    # Check timer counter start: DL_TimerA/G_startCounter must be called in main
    timer_issues = _check_timer_counter_start(all_content, project_dir)
    issues.extend(timer_issues)

    # Check ADC single-mode: enableConversions must appear before startConversion
    adc_issues = _check_adc_re_enable(all_content)
    issues.extend(adc_issues)

    # Check GPIO ISR: GROUP1_IRQHandler must clear interrupt status
    gpio_isr_issues = _check_gpio_isr_clear(all_content)
    issues.extend(gpio_isr_issues)

    oled_issues = _check_oled_usage(c_files)
    issues.extend(oled_issues)

    return issues, fixes


def _project_root_from_file(filepath: str) -> str:
    current = Path(filepath).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "User").is_dir() and (parent / "Project").is_dir():
            return str(parent)
    return os.path.dirname(os.path.dirname(filepath))


def _include_exists(project_dir: str, filepath: str, inc_path: str) -> bool:
    search_paths = [
        os.path.join(project_dir, inc_path),
        os.path.join(os.path.dirname(filepath), inc_path),
        os.path.join(project_dir, "BSP", inc_path),
        os.path.join(project_dir, "User", inc_path),
        os.path.join(project_dir, "Drive", inc_path),
        os.path.join(project_dir, "BSP", "OLED", inc_path),
        os.path.join(project_dir, "BSP", "delay", inc_path),
    ]
    if any(os.path.isfile(p) for p in search_paths):
        return True

    for subdir in ("BSP", "User", "Drive"):
        root = os.path.join(project_dir, subdir)
        if not os.path.isdir(root):
            continue
        for walk_root, _, files in os.walk(root):
            if inc_path in files:
                return True
    return False


def _check_oled_usage(c_files: List[str]) -> List[Dict]:
    issues = []
    oled_call = re.compile(
        r'\b(OLED_Show(?:String|Char|Num|CHinese))\s*\(\s*[^,]+,\s*(\d+)\s*,'
    )
    allowed_text_pages = {0, 2, 4, 6}

    for fpath in c_files:
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            continue

        fname = os.path.basename(fpath)
        norm = fpath.replace("/", "\\")
        if norm.endswith("\\BSP\\OLED\\spi0_oled.c") and re.search(
            r'\bOLED_(?:ClearWaveBuf|SetWavePixel|FlushWaveBuf)\b', content
        ):
            issues.append({
                "level": 3,
                "file": fname,
                "line": 0,
                "type": "custom_logic_in_oled_bsp",
                "message": "Keep BSP/OLED as the reference SH1106 driver; put app-specific drawing buffers in Drive/*.c/*.h.",
            })

        for lnum, line in enumerate(content.splitlines(), 1):
            for match in oled_call.finditer(line):
                func = match.group(1)
                page = int(match.group(2))
                if page not in allowed_text_pages:
                    issues.append({
                        "level": 3,
                        "file": fname,
                        "line": lnum,
                        "type": "oled_page_coordinate",
                        "message": f"{func} y argument is page {page}; use SH1106 pages 0, 2, 4, or 6 for 8x16 text, not pixel rows.",
                    })

    return issues


def _check_timer_counter_start(all_content: str, project_dir: str) -> List[Dict]:
    """Level 3: Verify DL_TimerA/G_startCounter is called for each configured timer."""
    issues = []
    # Find all timer instances from generated config
    timer_insts = set(re.findall(r'#define\s+(TIMER_\d+_INST)\s+', all_content))
    # Also find from DL_TimerA/G init calls
    timer_inits_A = re.findall(r'DL_TimerA_initTimerMode\(\s*(\w+)', all_content)
    timer_inits_G = re.findall(r'DL_TimerG_initTimerMode\(\s*(\w+)', all_content)
    start_calls = re.findall(r'DL_Timer([AG])_startCounter\(\s*(\w+)', all_content)

    started_insts = {m[1] for m in start_calls}

    all_configured = set(timer_insts) | set(timer_inits_A) | set(timer_inits_G)
    for inst in all_configured:
        if inst not in started_insts:
            issues.append({
                "level": 3, "file": "main.c", "line": 0,
                "type": "timer_not_started",
                "message": f"Timer {inst} is configured but DL_TimerA/G_startCounter({inst}) not called - counter will not run, ISR will never fire",
            })
    return issues


def _check_adc_re_enable(all_content: str) -> List[Dict]:
    """Level 3: In single mode, DL_ADC12_enableConversions must precede DL_ADC12_startConversion."""
    issues = []
    # Find functions containing DL_ADC12_startConversion
    func_pattern = re.compile(
        r'(?:void|static\s+void|static\s+inline\s+void)\s+(\w+)\s*\([^)]*\)\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}',
        re.DOTALL
    )
    for func_match in func_pattern.finditer(all_content):
        func_name = func_match.group(1)
        func_body = func_match.group(2)
        # Check for startConversion without preceding enableConversions
        start_positions = [m.start() for m in re.finditer(r'DL_ADC12_startConversion\(', func_body)]
        enable_positions = [m.start() for m in re.finditer(r'DL_ADC12_enableConversions\(', func_body)]
        if start_positions and not enable_positions:
            issues.append({
                "level": 3, "file": "main.c", "line": 0,
                "type": "adc_missing_enable_conversions",
                "message": f"Function '{func_name}()' calls DL_ADC12_startConversion but not DL_ADC12_enableConversions - ADC may only sample once in single mode",
            })
    return issues


def _check_gpio_isr_clear(all_content: str) -> List[Dict]:
    """Level 3: GROUP1_IRQHandler must call DL_GPIO_clearInterruptStatus or risk deadlock."""
    issues = []
    # Find GROUP1_IRQHandler function
    gpio_isr_match = re.search(
        r'void\s+GROUP1_IRQHandler\s*\([^)]*\)\s*\{(.*?)\n\}',
        all_content, re.DOTALL
    )
    if gpio_isr_match:
        isr_body = gpio_isr_match.group(1)
        if not re.search(r'DL_GPIO_clearInterruptStatus\(', isr_body):
            issues.append({
                "level": 3, "file": "main.c", "line": 0,
                "type": "gpio_isr_no_clear",
                "message": "GROUP1_IRQHandler defined but no DL_GPIO_clearInterruptStatus() - CPU will be trapped in infinite ISR loop (Cortex-M0+ re-enters if flag not cleared)",
            })
    return issues


def _strip_comments_and_strings(line: str) -> str:
    """Remove // comments and string literals from a line."""
    # Remove // comments
    idx = line.find("//")
    if idx >= 0:
        line = line[:idx]
    # Remove string literals (simplified)
    line = re.sub(r'"[^"]*"', '""', line)
    return line


def print_check_report(result: Dict) -> None:
    """Print a human-readable check report."""
    print("=" * 60)
    print("MSPM0G3519 代码质量检查报告")
    print("=" * 60)
    print(f"总问题数: {result['total_issues']}")
    print(f"  Level 1 (语法): {result['level1_syntax']}")
    print(f"  Level 2 (逻辑): {result['level2_logic']}")
    print(f"  Level 3 (平台): {result['level3_platform']}")
    print(f"  可自动修复: {result['auto_fixable']}")
    print(f"  需手动检查: {result['manual_review']}")
    print()

    if result["total_issues"] > 0:
        print("--- 问题详情 ---")
        for issue in result["issues"]:
            loc = f"{issue['file']}:{issue['line']}" if issue['line'] else issue['file']
            print(f"  [L{issue['level']}] {loc}: [{issue['type']}] {issue['message']}")
    else:
        print("  No issues found!")

    print("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MSPM0G3519 code quality checker")
    parser.add_argument("--project-dir", required=True, help="Project root directory")
    parser.add_argument("--level", type=int, default=3, choices=[1, 2, 3],
                        help="Check level (1=syntax, 2=logic, 3=platform)")
    parser.add_argument("--json-output", action="store_true", help="Output JSON")

    args = parser.parse_args()

    result = check_project(args.project_dir, args.level)

    if args.json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_check_report(result)

    if result["total_issues"] > 0:
        sys.exit(1)
