"""
Resolve user-friendly STM32 chip names to CubeMX internal Mcu.Name and Package.

The CubeMX MCU database (db/mcu/*.xml) uses pattern-based naming like:
  - STM32F407Z(E-G)Tx.xml  → covers ZET (512KB) to ZGT (1MB)
  - STM32H743VITx.xml       → exact match for VIT6
  - STM32G431C(6-8-B)Tx.xml → covers C6/C8/CB variants

This module parses user chip names (e.g., STM32F407ZGT6) and finds the matching
CubeMX XML file, returning the Mcu.Name (RefName) and Package for .ioc generation.
"""
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Dict, List, Tuple


# STM32 part number parsing regex
# STM32 F 407 Z G T 6
#       | |   | | | +-- temperature/options
#       | |   | | +---- package type: T=LQFP, H=BGA, I=UFBGA, U=UFQFPN, Y=WLCSP
#       | |   | +------ flash size: 4/6/8/B/C/D/E/F/G/H/I
#       | |   +-------- pin count: C=48, R=64, M=?, V=100, Z=144, I=176+, A=169
#       | +------------ subfamily: 03/07/11/15/29/31/41/43/46/47/74/...
#       +-------------- family: F1/F2/F4/G0/G4/H7/L0/L1/L4/WB/WL
#
_STM32_PATTERN = re.compile(
    r'^STM32'
    r'(?P<family>[A-Z]\d)'
    r'(?P<subfamily>\d{2,3})'
    r'(?P<package>[A-Z]\d?)'
    r'(?P<flash>[A-Z\d])'
    r'(?P<package_type>[A-Z])'
    r'(?P<options>.*)$',
    re.IGNORECASE
)


def parse_chip(chip: str) -> Optional[Dict]:
    """Parse a standard STM32 part number into components."""
    m = _STM32_PATTERN.match(chip.strip().upper())
    if not m:
        return None
    return {
        "family": m.group("family").upper(),
        "subfamily": m.group("subfamily"),
        "package": m.group("package").upper(),
        "flash": m.group("flash").upper(),
        "package_type": m.group("package_type").upper(),
        "options": m.group("options"),
        "full": chip.strip().upper(),
    }


def resolve_cubemx_mcu(chip: str, cubemx_db_path: Optional[str] = None) -> Optional[Dict]:
    """Resolve a chip name to CubeMX Mcu.Name and Package.

    Args:
        chip: Standard STM32 part number (e.g., STM32F407ZGT6)
        cubemx_db_path: Path to CubeMX db/mcu/ directory. Auto-detected if None.

    Returns:
        Dict with keys: cubemx_name, cubemx_package, family, or None if not found.
    """
    parsed = parse_chip(chip)
    if not parsed:
        return None

    if cubemx_db_path is None:
        cubemx_exe = _find_cubemx_exe()
        if not cubemx_exe:
            return None
        cubemx_db_path = os.path.join(os.path.dirname(cubemx_exe), "db", "mcu")

    if not os.path.isdir(cubemx_db_path):
        return None

    # Build search prefix: STM32 + family + subfamily + package_letter
    # e.g., STM32F407Z for STM32F407ZGT6
    prefix = f"STM32{parsed['family']}{parsed['subfamily']}{parsed['package']}"

    # Find all XML files matching this prefix
    candidates = []
    for fname in os.listdir(cubemx_db_path):
        if not fname.endswith(".xml"):
            continue
        name_no_ext = fname[:-4]
        if name_no_ext.upper().startswith(prefix.upper()):
            candidates.append(fname)

    if not candidates:
        # Try broader search: just family+subfamily
        prefix2 = f"STM32{parsed['family']}{parsed['subfamily']}"
        for fname in os.listdir(cubemx_db_path):
            if not fname.endswith(".xml"):
                continue
            name_no_ext = fname[:-4]
            if name_no_ext.upper().startswith(prefix2.upper()):
                candidates.append(fname)

    if not candidates:
        return None

    # Score and match candidates against the parsed chip
    best = _best_match(candidates, parsed, cubemx_db_path)
    return best


def _find_cubemx_exe() -> Optional[str]:
    """Find CubeMX executable for database path discovery."""
    from cubemx_finder import find_cubemx
    return find_cubemx()


def _best_match(candidates: List[str], parsed: Dict, db_path: str) -> Optional[Dict]:
    """Find the best matching XML file for the parsed chip.

    Strategy:
    1. Try exact match (file name starts with chip prefix + flash letter)
    2. Try range match (file name contains (range) covering the flash letter)
    3. Fall back to first candidate with matching package letter
    """
    chip_pkg = parsed["package"]       # e.g., Z
    chip_flash = parsed["flash"]       # e.g., G
    chip_ptype = parsed["package_type"]  # e.g., T

    scored = []
    for fname in candidates:
        name_no_ext = fname[:-4]
        score = 0

        # Parse CubeMX filename pattern
        # Pattern: STM32F407Z(E-G)Tx or STM32H743VITx
        # Extract the variable part after the fixed prefix
        mx_info = _parse_cubemx_filename(name_no_ext)
        if not mx_info:
            continue

        # Check package letter match
        if mx_info["pkg_letter"].upper() == chip_pkg.upper():
            score += 100

        # Check if flash is in range
        if mx_info["flash_range"]:
            # e.g., "E-G" or "6-8-B"
            if _in_flash_range(chip_flash, mx_info["flash_range"]):
                score += 50
            else:
                continue  # flash not in range, skip
        elif mx_info.get("exact_flash"):
            # Exact match: filename has specific flash (like H743VITx → I)
            if mx_info["exact_flash"].upper() == chip_flash.upper():
                score += 50
            else:
                continue

        # Check package type suffix (Tx, Hx, Ix, Ux, Yx)
        if mx_info["pkg_suffix"].upper() == f"{chip_ptype}X":
            score += 25
        # Some patterns have "Tx" covering both T and other variants
        elif mx_info["pkg_suffix"].upper() == "TX" and chip_ptype in ("T",):
            score += 20

        # Prefer simpler names (fewer range groups = more specific)
        num_ranges = mx_info["filename"].count("(")
        score += (10 - num_ranges)

        mx_info["score"] = score
        scored.append(mx_info)

    if not scored:
        return None

    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)
    best = scored[0]

    # Now read the XML to get Package attribute
    xml_path = os.path.join(db_path, best["filename"])
    pkg = _read_package_from_xml(xml_path)
    family = _read_family_from_xml(xml_path)

    return {
        "cubemx_name": best["ref_name"],
        "cubemx_package": pkg,
        "family": family or f"STM32{parsed['family']}",
        "xml_file": best["filename"],
        "score": best["score"],
    }


def _parse_cubemx_filename(filename: str) -> Optional[Dict]:
    """Parse a CubeMX MCU XML filename into components.

    Examples:
      STM32F407Z(E-G)Tx → pkg_letter=Z, flash_range=E-G, pkg_suffix=Tx
      STM32H743VITx    → pkg_letter=V, exact_flash=I, pkg_suffix=Tx
      STM32G431C(6-8-B)Tx → pkg_letter=C, flash_range=6-8-B, pkg_suffix=Tx
    """
    # Remove .xml extension if present
    if filename.endswith(".xml"):
        filename = filename[:-4]

    # Pattern with range: STM32F407Z(E-G)Tx
    range_match = re.match(
        r'^(STM32\w+?)([A-Z]\d?)\(([^)]+)\)(\w+)$',
        filename, re.IGNORECASE
    )
    if range_match:
        prefix = range_match.group(1)
        pkg_letter = range_match.group(2)
        flash_range = range_match.group(3)
        pkg_suffix = range_match.group(4)
        # Extract ref_name = the full filename without extension
        return {
            "filename": filename + ".xml",
            "prefix": prefix,
            "pkg_letter": pkg_letter,
            "flash_range": flash_range,
            "pkg_suffix": pkg_suffix,
            "exact_flash": None,
            "ref_name": filename,
        }

    # Pattern without range: STM32H743VITx
    exact_match = re.match(
        r'^(STM32\w+?)([A-Z]\d?)([A-Z\d])(\w+)$',
        filename, re.IGNORECASE
    )
    if exact_match:
        prefix = exact_match.group(1)
        pkg_letter = exact_match.group(2)
        flash = exact_match.group(3)
        pkg_suffix = exact_match.group(4)
        return {
            "filename": filename + ".xml",
            "prefix": prefix,
            "pkg_letter": pkg_letter,
            "flash_range": None,
            "exact_flash": flash,
            "pkg_suffix": pkg_suffix,
            "ref_name": filename,
        }

    return None


def _in_flash_range(flash: str, flash_range: str) -> bool:
    """Check if a flash size code falls within a CubeMX flash range.

    Flash codes follow the STM32 ordering:
      4, 6, 8, B, C, D, E, F, G, H, I

    Range can be:
      "E-G"  → E through G
      "6-8-B" → 6 through 8 or B (multi-part range for G4 series)
      "B-C-E" → B through C or E (some G4 series have non-contiguous ranges)
    """
    flash_order = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if flash.upper() not in flash_order:
        return False

    flash_idx = flash_order.index(flash.upper())

    # Split range by dash: "E-G" → ["E", "G"]
    # For multi-part like "6-8-B", we check if flash is in any sub-range
    parts = flash_range.split("-")

    # Build list of valid flash codes from the range
    # First, check if this is a sequence like "E-G" or "E-G-I"
    # For multi-part like "6-8-B": 6-8 and also B on its own
    # For "B-C-E": B-C means B through C, but E is separate (non-contiguous)
    valid_codes = set()

    i = 0
    while i < len(parts):
        start = parts[i]
        if i + 1 < len(parts):
            # Check if this is a sub-range like "E-G" (both single letters)
            candidate_end = parts[i + 1]
            if (len(start) == 1 and len(candidate_end) == 1
                    and start in flash_order and candidate_end in flash_order):
                start_idx = flash_order.index(start)
                end_idx = flash_order.index(candidate_end)
                for j in range(start_idx, end_idx + 1):
                    valid_codes.add(flash_order[j])
                i += 2
                continue
        # Single code
        if len(start) == 1 and start in flash_order:
            valid_codes.add(start)
        i += 1

    return flash.upper() in valid_codes


def _read_package_from_xml(xml_path: str) -> Optional[str]:
    """Read the Package attribute from a CubeMX MCU XML file."""
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        return root.get("Package")
    except Exception:
        return None


def _read_family_from_xml(xml_path: str) -> Optional[str]:
    """Read the Family attribute from a CubeMX MCU XML file."""
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        return root.get("Family")
    except Exception:
        return None


def list_cubemx_mcus(cubemx_db_path: Optional[str] = None) -> List[str]:
    """List all MCU names supported by CubeMX (RefName from XML files)."""
    if cubemx_db_path is None:
        cubemx_exe = _find_cubemx_exe()
        if not cubemx_exe:
            return []
        cubemx_db_path = os.path.join(os.path.dirname(cubemx_exe), "db", "mcu")

    if not os.path.isdir(cubemx_db_path):
        return []

    names = []
    for fname in sorted(os.listdir(cubemx_db_path)):
        if not fname.endswith(".xml"):
            continue
        # Skip non-MCU files
        if fname in ("families.xml", "rules.xml", "compatibility.xml"):
            continue
        try:
            tree = ET.parse(os.path.join(cubemx_db_path, fname))
            root = tree.getroot()
            ref = root.get("RefName")
            if ref:
                names.append(ref)
        except Exception:
            continue

    return names


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Resolve STM32 chip names to CubeMX internal names")
    parser.add_argument("--chip", required=True,
                        help="Chip model (e.g., STM32F407ZGT6)")
    parser.add_argument("--db", default=None,
                        help="Path to CubeMX db/mcu/ directory (auto-detected if omitted)")
    parser.add_argument("--list", action="store_true",
                        help="List all CubeMX supported MCU RefNames")

    args = parser.parse_args()

    if args.list:
        names = list_cubemx_mcus(args.db)
        print(f"Found {len(names)} MCUs in CubeMX database:")
        for n in names[:50]:
            print(f"  {n}")
        if len(names) > 50:
            print(f"  ... and {len(names) - 50} more")
        sys.exit(0)

    result = resolve_cubemx_mcu(args.chip, args.db)
    if result:
        print(f"Chip: {args.chip}")
        print(f"  CubeMX Name (Mcu.Name): {result['cubemx_name']}")
        print(f"  CubeMX Package:         {result['cubemx_package']}")
        print(f"  Family:                 {result['family']}")
        print(f"  XML file:               {result['xml_file']}")
        print(f"  Match score:            {result['score']}")
    else:
        print(f"Could not resolve {args.chip} in CubeMX database.")
        parsed = parse_chip(args.chip)
        if parsed:
            print(f"  Parsed: family={parsed['family']}, "
                  f"subfamily={parsed['subfamily']}, "
                  f"package={parsed['package']}, "
                  f"flash={parsed['flash']}, "
                  f"pkg_type={parsed['package_type']}")
        sys.exit(1)
