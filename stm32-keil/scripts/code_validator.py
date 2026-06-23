"""
Validate STM32 source code before compilation.
Checks for common issues like empty main loop, missing includes, etc.
"""
import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Optional, NamedTuple
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """Result of code validation."""
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)


def validate_main_c(
    main_c_path: str,
    expected_peripherals: Optional[List[str]] = None,
) -> ValidationResult:
    """
    Validate main.c for common issues before compilation.

    Args:
        main_c_path: Path to main.c
        expected_peripherals: List of peripherals that should be initialized
            (e.g., ["USART1", "TIM2", "ADC1"])

    Returns:
        ValidationResult with errors/warnings/info
    """
    result = ValidationResult(passed=True)

    if not os.path.isfile(main_c_path):
        result.passed = False
        result.errors.append(f"File not found: {main_c_path}")
        return result

    with open(main_c_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    lines = content.splitlines()
    content_lower = content.lower()

    # ─── Check 1: Empty while(1) loop ────────────────────────────────
    # Find the main while(1) loop and check if it has content
    in_main = False
    in_while = False
    while_depth = 0
    while_body_lines = []
    found_main = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Detect main function
        if re.match(r'(?:int|void)\s+main\s*\(', stripped):
            found_main = True
            in_main = True
            continue

        if in_main:
            # Track braces
            if '{' in stripped:
                while_depth += stripped.count('{')
            if '}' in stripped:
                while_depth -= stripped.count('}')

            # Detect while(1) or while (1) or for(;;)
            if re.match(r'while\s*\(\s*1\s*\)', stripped) or stripped == 'for(;;)':
                in_while = True
                continue

            if in_while and while_depth >= 2:
                # We're inside the while(1) body
                if stripped and not stripped.startswith('//') and not stripped.startswith('/*'):
                    while_body_lines.append(stripped)

            if while_depth <= 0:
                break

    if found_main and len(while_body_lines) == 0:
        result.passed = False
        result.errors.append(
            "main.c: while(1) 主循环是空的！必须有实际逻辑（LED闪烁、串口输出等）。"
            "模板的空 while(1) 能编译通过但板子上看不到任何效果。"
        )
    elif found_main and len(while_body_lines) < 2:
        result.warnings.append(
            "main.c: while(1) 主循环只有1行代码，确认是否完整。"
        )

    # ─── Check 2: Missing HAL_Init or Delay_Init ─────────────────────
    if 'hal_init()' not in content_lower and 'delay_init()' not in content_lower:
        if 'hal_init' not in content_lower:
            result.warnings.append("main.c: 没有调用 HAL_Init()（HAL 项目必须最先调用）")
        elif 'delay_init' not in content_lower:
            result.warnings.append("main.c: 没有调用 Delay_Init()（SPL 项目必须最先调用）")

    # ─── Check 3: Missing SystemClock_Config ─────────────────────────
    if 'systemclock_config' not in content_lower and 'clock_init' not in content_lower:
        result.warnings.append("main.c: 没有 SystemClock_Config() 或 Clock_Init() 调用")

    # ─── Check 4: Expected peripheral init calls ─────────────────────
    if expected_peripherals:
        for periph in expected_peripherals:
            # Check for _Init() call (e.g., USART1_Init, MX_USART1_UART_Init)
            periph_lower = periph.lower()
            init_patterns = [
                f'{periph_lower}_init',
                f'mx_{periph_lower}_init',
                f'{periph_lower}_config',
            ]
            found = any(p in content_lower for p in init_patterns)
            if not found:
                result.warnings.append(
                    f"main.c: 没找到 {periph} 的初始化调用（期望 {periph}_Init() 或类似）"
                )

    # ─── Check 5: printf without USART setup ─────────────────────────
    if 'printf' in content and 'usart' not in content_lower:
        result.warnings.append(
            "main.c: 使用了 printf 但没有 USART 相关代码，"
            "printf 输出需要重定向到 USART"
        )

    # ─── Check 6: Missing Error_Handler for HAL ──────────────────────
    if 'hal_' in content_lower and 'error_handler' not in content_lower:
        result.info.append("main.c: HAL 项目建议定义 Error_Handler() 函数")

    # ─── Check 7: Check for _it.c interrupt handlers ─────────────────
    # This is checked at project level, not main.c level

    return result


def validate_project(
    project_dir: str,
    expected_peripherals: Optional[List[str]] = None,
) -> ValidationResult:
    """
    Validate an entire STM32 project before compilation.

    Args:
        project_dir: Root directory of the project
        expected_peripherals: List of peripherals that should be initialized

    Returns:
        ValidationResult
    """
    result = ValidationResult(passed=True)

    # Find main.c
    main_c_candidates = [
        os.path.join(project_dir, "User", "main.c"),
        os.path.join(project_dir, "Src", "main.c"),
        os.path.join(project_dir, "main.c"),
    ]
    main_c_path = None
    for p in main_c_candidates:
        if os.path.isfile(p):
            main_c_path = p
            break

    if main_c_path is None:
        result.passed = False
        result.errors.append(f"找不到 main.c（已查找: {', '.join(main_c_candidates)}）")
        return result

    # Validate main.c
    main_result = validate_main_c(main_c_path, expected_peripherals)
    result.errors.extend(main_result.errors)
    result.warnings.extend(main_result.warnings)
    result.info.extend(main_result.info)
    if not main_result.passed:
        result.passed = False

    # Check for .uvprojx
    uvprojx_found = False
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in ("Objects", "Listings", "__pycache__")]
        for f in files:
            if f.endswith(".uvprojx"):
                uvprojx_found = True
                break
        if uvprojx_found:
            break

    if not uvprojx_found:
        result.warnings.append("项目中没有找到 .uvprojx 文件")

    return result


def format_validation_report(result: ValidationResult) -> str:
    """Format validation result as a readable report."""
    lines = []

    if result.passed:
        lines.append("✓ 代码验证通过")
    else:
        lines.append("✗ 代码验证失败")

    if result.errors:
        lines.append(f"\n错误 ({len(result.errors)}):")
        for e in result.errors:
            lines.append(f"  ✗ {e}")

    if result.warnings:
        lines.append(f"\n警告 ({len(result.warnings)}):")
        for w in result.warnings:
            lines.append(f"  ! {w}")

    if result.info:
        lines.append(f"\n提示 ({len(result.info)}):")
        for i in result.info:
            lines.append(f"  i {i}")

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Validate STM32 project code before compilation")
    parser.add_argument("--project", required=True, help="Project root directory")
    parser.add_argument("--peripherals", default="", help="Comma-separated expected peripherals")
    parser.add_argument("--main-c", default="", help="Direct path to main.c (overrides auto-detect)")
    args = parser.parse_args()

    periph = [p.strip() for p in args.peripherals.split(",") if p.strip()] or None

    if args.main_c:
        result = validate_main_c(args.main_c, periph)
    else:
        result = validate_project(args.project, periph)

    print(format_validation_report(result))
    sys.exit(0 if result.passed else 1)
