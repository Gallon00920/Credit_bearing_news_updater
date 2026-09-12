#!/usr/bin/env python3
"""Append a reviewed report JSON object to data/golden_cases.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GOLDEN_CASES_PATH = ROOT / "data" / "golden_cases.json"


def main() -> int:
    payload = read_payload()
    data = load_golden_cases()
    cases = data.setdefault("cases", [])
    key = case_key(payload)
    if any(case_key(case) == key for case in cases):
        print("Golden case already exists; no change.")
        return 0
    cases.append(payload)
    GOLDEN_CASES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Added golden case for: {payload.get('title', payload.get('itemId', 'untitled'))}")
    return 0


def read_payload() -> dict:
    if len(sys.argv) > 1:
        raw = Path(sys.argv[1]).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Expected one JSON object")
    return payload


def load_golden_cases() -> dict:
    if GOLDEN_CASES_PATH.exists():
        return json.loads(GOLDEN_CASES_PATH.read_text(encoding="utf-8"))
    return {"cases": []}


def case_key(case: dict) -> tuple[str, str, str]:
    return (
        str(case.get("itemId") or ""),
        str(case.get("url") or ""),
        str(case.get("reasonType") or ""),
    )


if __name__ == "__main__":
    raise SystemExit(main())
