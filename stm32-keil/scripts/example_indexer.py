"""
Build and query a cached index for skeleton/example code.

The raw examples tree can be large. This index keeps only paths, detected
family, peripheral tags, and lightweight scores so agents can route quickly
before opening specific files.
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from example_searcher import PERIPHERAL_KEYWORDS


SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_EXAMPLES = SKILL_DIR / "skeleton"
DEFAULT_INDEX = SKILL_DIR / "data" / "example_index.json"
SOURCE_EXTS = {".c", ".h", ".cpp", ".hpp", ".s", ".S"}
MAX_SCAN_BYTES = 512 * 1024


def _detect_family(path: str, text: str) -> str:
    blob = (path + "\n" + text[:4096]).lower()
    if "stm32f10x" in blob or "f103" in blob:
        return "F103"
    if "stm32f4xx" in blob or "stm32f40" in blob or "f407" in blob:
        return "F407"
    if "stm32g4" in blob:
        return "G4"
    if "stm32l4" in blob:
        return "L4"
    if "stm32h7" in blob:
        return "H7"
    if "stm32c0" in blob:
        return "C0"
    return "unknown"


def _score_peripherals(text: str) -> Dict[str, int]:
    lower = text.lower()
    scores = {}
    for peripheral, keywords in PERIPHERAL_KEYWORDS.items():
        score = sum(lower.count(k.lower()) for k in keywords)
        if score:
            scores[peripheral] = score
    return scores


def _iter_source_files(root: Path) -> Iterable[Path]:
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d.lower() not in {".git", "objects", "listings"}]
        for name in files:
            path = Path(current) / name
            if path.suffix in SOURCE_EXTS:
                yield path


def build_index(examples_dir: str = str(DEFAULT_EXAMPLES),
                index_path: str = str(DEFAULT_INDEX)) -> Dict:
    root = Path(examples_dir)
    started = time.time()
    entries: List[Dict] = []
    peripheral_totals: Dict[str, int] = {}
    family_totals: Dict[str, int] = {}

    if not root.is_dir():
        raise FileNotFoundError(f"examples directory not found: {root}")

    for path in _iter_source_files(root):
        try:
            data = path.read_bytes()[:MAX_SCAN_BYTES]
            text = data.decode("utf-8", errors="ignore")
        except OSError:
            continue

        scores = _score_peripherals(text)
        if not scores:
            continue

        rel = str(path.relative_to(root)).replace("\\", "/")
        family = _detect_family(rel, text)
        best = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:6]
        entries.append({
            "file": rel,
            "family": family,
            "peripherals": [p for p, _ in best],
            "scores": dict(best),
            "size": path.stat().st_size,
        })
        family_totals[family] = family_totals.get(family, 0) + 1
        for peripheral in scores:
            peripheral_totals[peripheral] = peripheral_totals.get(peripheral, 0) + 1

    entries.sort(key=lambda e: (e["family"], e["file"]))
    index = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "examples_dir": str(root),
        "entry_count": len(entries),
        "family_totals": family_totals,
        "peripheral_totals": dict(sorted(peripheral_totals.items())),
        "entries": entries,
        "duration_sec": round(time.time() - started, 3),
    }

    out = Path(index_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    return index


def load_index(index_path: str = str(DEFAULT_INDEX)) -> Dict:
    path = Path(index_path)
    if not path.is_file():
        return build_index(str(DEFAULT_EXAMPLES), str(path))
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def query_index(peripheral: str = "", family: str = "", requirement: str = "",
                limit: int = 10, index_path: str = str(DEFAULT_INDEX)) -> List[Dict]:
    index = load_index(index_path)
    peripheral = peripheral.upper()
    family = family.upper()
    req_tokens = [t for t in re.split(r"[^A-Za-z0-9_]+", requirement.lower()) if len(t) >= 3]
    results = []
    for entry in index.get("entries", []):
        if family and entry.get("family", "").upper() != family:
            continue
        score = 0
        if peripheral:
            score += entry.get("scores", {}).get(peripheral, 0) * 10
            if score == 0:
                continue
        file_lower = entry.get("file", "").lower()
        score += sum(3 for token in req_tokens if token in file_lower)
        score += sum(entry.get("scores", {}).values())
        if score:
            item = dict(entry)
            item["rank_score"] = score
            results.append(item)
    results.sort(key=lambda e: e["rank_score"], reverse=True)
    return results[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build/query stm32-keil example index")
    parser.add_argument("--examples", default=str(DEFAULT_EXAMPLES))
    parser.add_argument("--index", default=str(DEFAULT_INDEX))
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--peripheral", default="")
    parser.add_argument("--family", default="")
    parser.add_argument("--requirement", default="")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    if args.build:
        idx = build_index(args.examples, args.index)
        print(json.dumps({k: v for k, v in idx.items() if k != "entries"},
                         indent=2, ensure_ascii=False))
        return 0

    results = query_index(args.peripheral, args.family, args.requirement,
                          args.limit, args.index)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
