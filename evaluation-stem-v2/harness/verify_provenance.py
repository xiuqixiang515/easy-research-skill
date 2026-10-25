#!/usr/bin/env python3
"""Provenance assertions: product revision, hashes, branch, and write-scope."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C


def git_blob_hash(source: Path, rev: str, rel: str) -> str:
    proc = __import__("subprocess").run(
        ["git", "show", f"{rev}:{rel}"], cwd=str(source), capture_output=True
    )
    return C.sha_bytes(proc.stdout) if proc.returncode == 0 else ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify provenance of an evaluation run")
    ap.add_argument("--source-root", default=str(C.DEFAULT_SOURCE))
    ap.add_argument("--product-rev", required=True)
    ap.add_argument("--expect-branch", default="eval/stem-v2")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    source = Path(args.source_root).resolve()
    lines, payload = [], {"schema": "eval-provenance/1", "checks": []}

    def add(name, ok, detail):
        lines.append(f"{name:<34}{detail:<24}{'OK' if ok else 'FAIL'}")
        payload["checks"].append({"name": name, "ok": bool(ok), "detail": detail})

    head = C.git(source, "rev-parse", "HEAD")
    add("product_rev", head == args.product_rev, head[:7])
    branch = C.git(source, "rev-parse", "--abbrev-ref", "HEAD")
    add("branch", branch == args.expect_branch, branch)

    hashes = C.product_hashes(source)
    mismatched = [rel for rel, value in hashes.items() if git_blob_hash(source, args.product_rev, rel) != value]
    add("product_hashes", not mismatched, f"{len(hashes) - len(mismatched)}/{len(hashes)}")
    payload["product_hashes"] = hashes

    status = [line for line in C.git(source, "status", "--porcelain").splitlines() if line.strip()]
    outside = [line for line in status if not line[3:].startswith("evaluation-stem-v2/")]
    add("writes confined to eval dir", not outside, f"{len(status)} entries")
    payload["status_entries"] = status

    harness = {p.name: C.sha_file(p) for p in sorted((C.HARNESS_DIR).glob("*.py"))}
    bundle = C.sha_text(json.dumps(harness, sort_keys=True))
    add("harness_bundle_sha256", bool(bundle), bundle[:12])
    protocol = C.protocol_digest()
    add("protocol_sha256", bool(protocol), protocol[:12])
    payload.update({"harness_sha256": harness, "harness_bundle_sha256": bundle, "protocol_sha256": protocol})

    main_tip = C.git(source, "rev-parse", "main")
    add("main tip unchanged", main_tip == args.product_rev, main_tip[:7])

    if args.out:
        C.write_json(Path(args.out), payload)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("\n" + "\n".join(lines))
    return 0 if all(c["ok"] for c in payload["checks"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
