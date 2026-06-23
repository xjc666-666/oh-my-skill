"""
Analyze Cortex-M0+ HardFault register dumps.
Resolves PC/LR to function symbols from .map file.
"""
import os
import sys
import re
import json
from pathlib import Path
from typing import Dict, List, Optional


MSPM0G3519_CODE_RANGES = (
    (0x00000000, 0x00080000, "main flash"),
    (0x00400000, 0x00480000, "non-main flash/IROM2"),
)


def analyze_hardfault(registers: Dict, map_path: str) -> Dict:
    """Analyze HardFault register dump."""

    # Load .map file symbols
    symbols = _parse_map_file(map_path)
    if not symbols:
        return {"success": False, "error": f"Could not parse map file: {map_path}"}

    pc = int(registers.get("PC", "0"), 16) if isinstance(registers.get("PC"), str) else registers.get("PC", 0)
    lr = int(registers.get("LR", "0"), 16) if isinstance(registers.get("LR"), str) else registers.get("LR", 0)
    psr = int(registers.get("xPSR", "0"), 16) if isinstance(registers.get("xPSR"), str) else registers.get("xPSR", 0)
    cfsr = int(registers.get("CFSR", "0"), 16) if isinstance(registers.get("CFSR"), str) else registers.get("CFSR", 0)
    hfsr = int(registers.get("HFSR", "0"), 16) if isinstance(registers.get("HFSR"), str) else registers.get("HFSR", 0)

    pc_func = _resolve_symbol(symbols, pc)
    lr_func = _resolve_symbol(symbols, lr)

    # Cortex-M0+ diagnosis
    diagnosis = []
    forced = (hfsr >> 30) & 1  # FORCED bit
    vecttbl = (hfsr >> 1) & 1  # VECTTBL bit

    if vecttbl:
        diagnosis.append("VECTTBL: Vector table read error. Check if startup file is correct or if VTOR is set properly.")
    if forced:
        if cfsr & 0x01:
            diagnosis.append("IACCVIOL (Instruction access violation): PC may be pointing to invalid memory.")
        if cfsr & 0x02:
            diagnosis.append("DACCVIOL (Data access violation): Invalid memory access detected.")
        if cfsr & 0x0100:
            diagnosis.append("UNDEFINSTR (Undefined instruction): Executing data or corrupted instruction.")
        if cfsr & 0x0200:
            diagnosis.append("INVSTATE (Invalid state): Branch to non-thumb code address.")

    # MSPM0G3519 code is not at the STM32-style 0x08000000 range.
    # Treat addresses outside the device's executable flash ranges as suspicious.
    if pc == 0x00000000:
        diagnosis.append("PC is 0x00000000. Suspect a null function pointer, corrupted vector, or stack damage.")
    elif not _address_in_ranges(pc, MSPM0G3519_CODE_RANGES):
        diagnosis.append(
            "PC is outside MSPM0G3519 executable flash ranges "
            "(0x00000000-0x0007FFFF, 0x00400000-0x0047FFFF)."
        )
    if lr and not _is_exception_return(lr) and not _address_in_ranges(lr, MSPM0G3519_CODE_RANGES):
        diagnosis.append("LR is neither EXC_RETURN nor an address in executable flash. Suspect stack corruption.")
    if pc_func and "HardFault" in pc_func:
        diagnosis.append("Recursive HardFault: HardFault occurred inside HardFault Handler.")

    exception_number = psr & 0x1FF
    if exception_number and exception_number != 3:
        diagnosis.append(f"xPSR exception number is {exception_number}; expected 3 while inside HardFault.")

    if not diagnosis:
        diagnosis.append(
            "Unknown fault cause. Cortex-M0+ has limited fault status registers; inspect PC/LR, stack, "
            "recent ISR code, invalid pointers, and peripheral register access order."
        )

    return {
        "success": True,
        "pc": f"0x{pc:08X}",
        "pc_function": pc_func,
        "pc_offset": f"0x{pc - symbols[pc_func]:X}" if pc_func and pc_func in symbols else "",
        "lr": f"0x{lr:08X}",
        "lr_function": lr_func,
        "psr": f"0x{psr:08X}",
        "cfsr": f"0x{cfsr:08X}",
        "hfsr": f"0x{hfsr:08X}",
        "forced": bool(forced),
        "vecttbl_error": bool(vecttbl),
        "diagnosis": diagnosis,
    }


def _parse_map_file(map_path: str) -> Dict[str, int]:
    """Parse Keil .map file and extract symbol -> address mapping."""
    if not os.path.isfile(map_path):
        return {}

    symbols = {}
    try:
        with open(map_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return {}

    # ARM linker .map format: address  size  type  name
    # 0x00001234  0x00000080  Code  RO  main.o(.text)
    # Also: entry points: symbol  0x00001234
    for line in content.split("\n"):
        # Match symbol table entries
        m = re.match(r'\s*(0x[0-9A-Fa-f]+)\s+\w+\s+(\w+)', line)
        if m:
            addr = int(m.group(1), 16)
            name = m.group(2)
            symbols[name] = addr

        # Match "section layout" items: symbol  0x00001234  ...
        m = re.match(r'\s+(\w+)\s+(0x[0-9A-Fa-f]+)\s+', line)
        if m and not m.group(1).startswith("0x"):
            addr = int(m.group(2), 16)
            symbols[m.group(1)] = addr

    return symbols


def _resolve_symbol(symbols: Dict[str, int], addr: int) -> Optional[str]:
    """Find the function containing the given address."""
    best_name = None
    best_addr = 0

    for name, sym_addr in symbols.items():
        if sym_addr <= addr and sym_addr > best_addr:
            best_name = name
            best_addr = sym_addr

    return best_name


def _address_in_ranges(addr: int, ranges) -> bool:
    """Return True if addr falls within any half-open address range."""
    return any(start <= addr < end for start, end, _name in ranges)


def _is_exception_return(addr: int) -> bool:
    """Cortex-M EXC_RETURN values have the 0xFFFFFFxx pattern."""
    return (addr & 0xFFFFFF00) == 0xFFFFFF00


def generate_hardfault_handler_c() -> str:
    """Generate MSPM0G3519 HardFault_Handler C code."""
    return '''#include <stdint.h>
#include <stdio.h>

void HardFault_HandlerC(uint32_t *stack);

__attribute__((naked)) void HardFault_Handler(void)
{
    __asm volatile(
        "movs r0, #4\\n"
        "mov r1, lr\\n"
        "tst r0, r1\\n"
        "beq 1f\\n"
        "mrs r0, psp\\n"
        "b 2f\\n"
        "1:\\n"
        "mrs r0, msp\\n"
        "2:\\n"
        "b HardFault_HandlerC\\n"
    );
}

void HardFault_HandlerC(uint32_t *stack)
{
    printf("HardFault\\r\\n");
    printf("R0=0x%08lX R1=0x%08lX R2=0x%08lX R3=0x%08lX\\r\\n",
           (unsigned long)stack[0], (unsigned long)stack[1],
           (unsigned long)stack[2], (unsigned long)stack[3]);
    printf("R12=0x%08lX LR=0x%08lX PC=0x%08lX xPSR=0x%08lX\\r\\n",
           (unsigned long)stack[4], (unsigned long)stack[5],
           (unsigned long)stack[6], (unsigned long)stack[7]);

    while (1) {
    }
}
'''


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MSPM0G3519 HardFault Analyzer")
    parser.add_argument("--registers", help='JSON: {"PC":"0x00001234","LR":"0x...","xPSR":"..."}')
    parser.add_argument("--map", help="Path to .map file")
    parser.add_argument("--gen-handler", action="store_true", help="Generate HardFault_Handler code")

    args = parser.parse_args()

    if args.gen_handler:
        print(generate_hardfault_handler_c())
    else:
        if not args.registers or not args.map:
            parser.error("--registers and --map are required unless --gen-handler is used")
        regs = json.loads(args.registers)
        result = analyze_hardfault(regs, args.map)
        print(json.dumps(result, indent=2, ensure_ascii=False))
