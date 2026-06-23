"""
Pin recommendation engine for STM32 projects.
Given a list of peripherals, automatically recommends optimal pin assignments
and checks for conflicts.
"""
import os
import sys
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import load_family_config, get_family_for_chip, load_chip_db
from pin_conflict_checker import load_pin_mapping, check_pin_conflicts, format_conflict_table


def recommend_pins(
    family: str,
    peripherals: List[str],
    pin_db: Optional[Dict] = None,
) -> Dict[str, List[Dict]]:
    """
    Recommend pin assignments for a list of peripherals.

    Args:
        family: Chip family (F103, F407, G4, L4, H7, C0)
        peripherals: List of peripheral specs like ["USART1", "SPI1", "TIM2_CH1", "ADC1_IN0"]
        pin_db: Pin mapping database (auto-loaded if None)

    Returns:
        Dict mapping peripheral spec to list of possible pin assignments
    """
    if pin_db is None:
        pin_db = load_pin_mapping(family)

    pins_data = pin_db.get("pins", {})
    results = {}

    for periph_spec in peripherals:
        # Parse peripheral spec: "USART1_TX", "SPI1", "TIM2_CH1", "ADC1_IN0"
        parts = periph_spec.upper().split("_", 1)
        periph_name = parts[0]
        signal = parts[1] if len(parts) > 1 else ""

        candidates = []

        for pin_name, pin_info in pins_data.items():
            for func in pin_info.get("functions", []):
                func_periph = func.get("peripheral", "").upper()
                func_signal = func.get("signal", "").upper()

                # Match peripheral
                if func_periph == periph_name:
                    # If signal specified, must match
                    if signal and func_signal != signal:
                        continue
                    candidates.append({
                        "pin": pin_name,
                        "peripheral": func_periph,
                        "signal": func_signal,
                        "af": func.get("af", -1),
                        "5v_tolerant": pin_info.get("5v_tolerant", True),
                        "jtag_swd": pin_info.get("jtag_swd", False),
                    })

        # Sort: prefer non-JTAG pins, then 5V tolerant
        candidates.sort(key=lambda c: (c["jtag_swd"], not c["5v_tolerant"]))

        results[periph_spec] = candidates

    return results


def auto_assign_pins(
    family: str,
    peripherals: List[str],
) -> Tuple[Dict[str, str], List[str]]:
    """
    Automatically assign pins to peripherals, avoiding conflicts.

    Args:
        family: Chip family
        peripherals: List of peripheral specs

    Returns:
        Tuple of (assignments dict, warnings list)
        assignments: {"USART1_TX": "PA9", "USART1_RX": "PA10", ...}
        warnings: list of issues
    """
    recommendations = recommend_pins(family, peripherals)
    assignments = {}
    used_pins = set()
    warnings = []

    for periph_spec, candidates in recommendations.items():
        if not candidates:
            warnings.append(f"没有找到 {periph_spec} 的可用引脚")
            continue

        # Find first unused pin
        assigned = False
        for cand in candidates:
            pin = cand["pin"]
            if pin not in used_pins:
                assignments[periph_spec] = pin
                used_pins.add(pin)
                assigned = True
                break

        if not assigned:
            # All candidates are used, pick the least conflicting one
            best = candidates[0]
            assignments[periph_spec] = best["pin"]
            warnings.append(
                f"{periph_spec}: 所有候选引脚都被占用，使用 {best['pin']}（可能冲突）"
            )

    return assignments, warnings


def format_recommendations(
    family: str,
    peripherals: List[str],
    max_candidates: int = 3,
) -> str:
    """
    Format pin recommendations as a readable table.

    Args:
        family: Chip family
        peripherals: List of peripheral specs
        max_candidates: Max number of candidate pins to show per peripheral

    Returns:
        Formatted string
    """
    recommendations = recommend_pins(family, peripherals)
    assignments, auto_warnings = auto_assign_pins(family, peripherals)

    lines = [
        f"引脚推荐 ({family})",
        "=" * 70,
        "",
        "推荐分配:",
        f"{'外设':<20} {'推荐引脚':<10} {'AF':<5} {'5V容限':<8} {'备选'}",
        "-" * 70,
    ]

    for periph_spec, candidates in recommendations.items():
        assigned_pin = assignments.get(periph_spec, "?")
        assigned_af = ""
        assigned_5v = ""

        for c in candidates:
            if c["pin"] == assigned_pin:
                assigned_af = str(c["af"]) if c["af"] >= 0 else "IO"
                assigned_5v = "是" if c["5v_tolerant"] else "否"
                break

        # Get alternative pins
        alts = [c["pin"] for c in candidates if c["pin"] != assigned_pin][:max_candidates]
        alt_str = ", ".join(alts) if alts else "-"

        lines.append(f"{periph_spec:<20} {assigned_pin:<10} {assigned_af:<5} {assigned_5v:<8} {alt_str}")

    # Add conflict check
    lines.append("")
    lines.append("冲突检查:")
    lines.append("-" * 70)

    conflict_input = []
    for periph_spec, pin in assignments.items():
        parts = periph_spec.upper().split("_", 1)
        periph_name = parts[0]
        signal = parts[1] if len(parts) > 1 else ""
        conflict_input.append({
            "peripheral": periph_name,
            "signal": signal,
            "pin": pin,
        })

    try:
        conflicts = check_pin_conflicts(family, conflict_input)
        conflict_report = format_conflict_table(conflicts)
        lines.append(conflict_report)
    except Exception as e:
        lines.append(f"冲突检查失败: {e}")

    if auto_warnings:
        lines.append("")
        lines.append("警告:")
        for w in auto_warnings:
            lines.append(f"  ! {w}")

    # Add usage example
    lines.append("")
    lines.append("使用方法 (Agent 可直接复制):")
    lines.append("-" * 70)
    lines.append("确认引脚表格:")
    lines.append("")
    lines.append(f"| {'模块':<12} | {'引脚':<8} | {'GPIO':<8} | {'说明'} |")
    lines.append(f"|{'-'*14}|{'-'*10}|{'-'*10}|{'-'*12}|")

    for periph_spec, pin in assignments.items():
        parts = periph_spec.upper().split("_", 1)
        periph_name = parts[0]
        signal = parts[1] if len(parts) > 1 else ""
        gpio_port = pin[:2] + "PIO" if len(pin) >= 2 else "?"
        desc = f"{periph_name} {signal}" if signal else periph_name
        lines.append(f"| {periph_name:<12} | {pin:<8} | {gpio_port:<8} | {desc} |")

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="STM32 pin recommendation engine")
    parser.add_argument("--family", required=True,
                        help="Chip family (F103, F407, F411, F429, G4, L4, H7, C0)")
    parser.add_argument("--peripherals", required=True,
                        help="Comma-separated peripheral specs (e.g., USART1,SPI1,TIM2_CH1)")
    parser.add_argument("--max-candidates", type=int, default=3,
                        help="Max candidate pins to show per peripheral")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON instead of table")
    args = parser.parse_args()

    periph_list = [p.strip() for p in args.peripherals.split(",") if p.strip()]

    if args.json:
        recommendations = recommend_pins(args.family, periph_list)
        assignments, warnings = auto_assign_pins(args.family, periph_list)
        output = {
            "family": args.family,
            "peripherals": periph_list,
            "assignments": assignments,
            "recommendations": {k: v[:args.max_candidates] for k, v in recommendations.items()},
            "warnings": warnings,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(format_recommendations(args.family, periph_list, args.max_candidates))
