#!/usr/bin/env python3
"""Compare the Skill arm and the no-Skill control arm on the seven B1 tasks."""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C
import grade_text as G

SLUGS = ["computer", "chemistry", "biology", "medicine", "mechanical", "energy", "electronics"]
ITEMS = [k for k in G.ITEMS if k != "S4"]


def role_b1(text: str) -> str:
    match = re.search(r"^## 4 B1.*?$(.*?)(?=^## )", text, re.S | re.M)
    return match.group(1).strip() if match else ""


def control_sections(text: str) -> dict:
    blocks = re.split(r"^## \d+ ", text, flags=re.M)[1:]
    return {slug: block.strip() for slug, block in zip(SLUGS, blocks)}


def score(text: str, slug: str) -> dict:
    graded = G.grade(text, slug, keywords=[])
    return {"chars": len(text), "items": {k: graded["items"][k] for k in ITEMS},
            "errors": graded["errors"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--roles", required=True)
    ap.add_argument("--control", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    control = control_sections(Path(args.control).read_text(encoding="utf-8-sig"))
    rows, skill, ctrl = [], {}, {}
    for slug in SLUGS:
        s_text = role_b1(Path(args.roles, f"{slug}.md").read_text(encoding="utf-8-sig"))
        c_text = control.get(slug, "")
        s, c = score(s_text, slug), score(c_text, slug)
        skill[slug], ctrl[slug] = s, c
        rows.append({"slug": slug, "skill_chars": s["chars"], "control_chars": c["chars"],
                     "skill_items": s["items"], "control_items": c["items"],
                     "skill_errors": s["errors"], "control_errors": c["errors"]})

    def tally(arm: dict, key: str) -> dict:
        return {item: f"{sum(1 for s in arm.values() if s['items'][item])}/{len(arm)}" for item in ITEMS}

    payload = {
        "schema": "eval-arms/1",
        "note": "S4 excluded: no shared keyword list across seven different B1 tasks",
        "skill": tally(skill, "items"),
        "control": tally(ctrl, "items"),
        "skill_errors": {k: f"{sum(1 for s in skill.values() if s['errors'][k])}/7" for k in G.ERRORS},
        "control_errors": {k: f"{sum(1 for s in ctrl.values() if s['errors'][k])}/7" for k in G.ERRORS},
        "rows": rows,
    }
    C.write_json(Path(args.out), payload)
    print(json.dumps({"skill": payload["skill"], "control": payload["control"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
