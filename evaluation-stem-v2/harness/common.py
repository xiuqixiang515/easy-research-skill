#!/usr/bin/env python3
"""Shared helpers for the evaluation harness (read-only with respect to product source)."""
from __future__ import annotations
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SCHEMA = "eval-results/2"
HARNESS_DIR = Path(__file__).resolve().parent
EVAL_DIR = HARNESS_DIR.parent
DEFAULT_SOURCE = EVAL_DIR.parent
TEMP = EVAL_DIR / "temp-data"

PRODUCT_FILES = [
    "SKILL.md",
    "VERSION",
    "CHANGELOG.md",
    "references/idea-generation.md",
    "references/demystify.md",
    "references/sharpen.md",
    "references/search-sources.md",
    "references/report-template.md",
    "scripts/idea_card.py",
    "scripts/report_render.py",
]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def sha_text(text: str) -> str:
    return sha_bytes(text.encode("utf-8"))


def product_hashes(source: Path) -> dict:
    return {rel: sha_file(source / rel) for rel in PRODUCT_FILES if (source / rel).is_file()}


def git(source: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(source), capture_output=True, text=True, encoding="utf-8"
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def child_env(guard_db: Path) -> dict:
    env = os.environ.copy()
    env.update(
        PYTHONUTF8="1",
        PYTHONIOENCODING="utf-8",
        PYTHONDONTWRITEBYTECODE="1",
        EASY_RESEARCH_DB=str(guard_db),
    )
    return env


def run_cmd(source: Path, script: str, args: list, guard_db: Path, timeout: int = 30) -> dict:
    """Run a product CLI script and capture a structured observation."""
    argv = [sys.executable, "-X", "utf8", str(source / "scripts" / script), *map(str, args)]
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            argv,
            cwd=str(source),
            env=child_env(guard_db),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
        )
        exit_code, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        exit_code, out, err = None, "", f"timeout after {timeout} seconds"
    seconds = time.perf_counter() - started
    return {
        "argv": argv,
        "cwd": str(source),
        "exit_code": exit_code,
        "stdout": out,
        "stderr": err,
        "seconds": round(seconds, 4),
    }


def excerpt(text: str, limit: int = 40) -> str:
    lines = text.splitlines()
    return "\n".join(lines[:limit])


def evaluate(observed: dict, expected: dict, db: Path | None = None, db_before: str | None = None) -> tuple[bool, list[str]]:
    """Check an observation against a structured expectation."""
    notes = []
    ok = True
    if "exit_code" in expected:
        if observed["exit_code"] != expected["exit_code"]:
            ok = False
            notes.append(f"exit_code {observed['exit_code']} != {expected['exit_code']}")
    for needle in expected.get("stdout_contains", []):
        if needle not in observed["stdout"]:
            ok = False
            notes.append(f"stdout missing: {needle}")
    for needle in expected.get("stderr_contains", []):
        if needle not in observed["stderr"]:
            ok = False
            notes.append(f"stderr missing: {needle}")
    if "stderr_not_contains" in expected:
        for needle in expected["stderr_not_contains"]:
            if needle in observed["stderr"]:
                ok = False
                notes.append(f"stderr unexpectedly contains: {needle}")
    if "stdout_count" in expected:
        for needle, count in expected["stdout_count"].items():
            actual = observed["stdout"].count(needle)
            if actual != count:
                ok = False
                notes.append(f"stdout count({needle}) {actual} != {count}")
    if expected.get("db_unchanged") and db is not None:
        if db_before is None or not db.exists() or sha_file(db) != db_before:
            ok = False
            notes.append("database changed unexpectedly")
    if expected.get("db_absent") and db is not None and db.exists():
        ok = False
        notes.append("database was created unexpectedly")
    return ok, notes


def record(case: str, observed: dict, expected: dict, passed: bool, notes: list[str]) -> dict:
    return {
        "case": case,
        "command_argv": observed["argv"],
        "cwd": observed["cwd"],
        "exit_code": observed["exit_code"],
        "stdout_excerpt": excerpt(observed["stdout"]),
        "stdout_sha256": sha_text(observed["stdout"]),
        "stdout_lines": len(observed["stdout"].splitlines()),
        "stderr_excerpt": excerpt(observed["stderr"], 20),
        "seconds": observed["seconds"],
        "expected": expected,
        "passed": passed,
        "notes": notes,
    }


def envelope(source: Path, harness_names: list[str], protocol_sha: str, extra: dict | None = None) -> dict:
    harness = {name: sha_file(HARNESS_DIR / name) for name in harness_names if (HARNESS_DIR / name).is_file()}
    bundle = sha_text(json.dumps(harness, sort_keys=True))
    tag = git(source, "describe", "--tags", "--abbrev=0", "--match", "v*")
    body = {
        "schema": SCHEMA,
        "started_at": now_iso(),
        "git_rev": git(source, "rev-parse", "HEAD"),
        "git_describe": git(source, "describe", "--tags", "--always"),
        "product_tag": tag,
        "product_tag_commit": git(source, "rev-list", "-n", "1", tag) if tag else "",
        "branch": git(source, "rev-parse", "--abbrev-ref", "HEAD"),
        "source_root": str(source),
        "product_hashes": product_hashes(source),
        "harness_sha256": harness,
        "harness_bundle_sha256": bundle,
        "protocol_sha256": protocol_sha,
        "python": sys.version.replace("\n", " "),
        "python_in_ci_matrix": sys.version_info[:2] in {(3, 11), (3, 12)},
        "platform": platform.platform(),
        "executable": sys.executable,
    }
    if extra:
        body.update(extra)
    return body


def protocol_digest() -> str:
    path = EVAL_DIR / "protocol.md"
    return sha_file(path) if path.is_file() else ""


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def require_branch(source: Path, expect: str) -> None:
    branch = git(source, "rev-parse", "--abbrev-ref", "HEAD")
    if expect and branch != expect:
        raise SystemExit(f"refusing to run: branch {branch!r} != expected {expect!r}")


def guard_paths(source: Path, base: Path) -> None:
    """Allow writes only inside <source>/evaluation-stem-v2/ (never into product files)."""
    src = source.resolve()
    dst = base.resolve()
    eval_dir = (src / "evaluation-stem-v2").resolve()
    if dst != eval_dir and eval_dir not in dst.parents:
        raise SystemExit(f"refusing to write outside evaluation dir: {dst}")


def ensure_fresh(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise SystemExit(f"refusing to reuse existing artifacts: {path}")


def normalize_weekly(text: str) -> str:
    import re

    text = re.sub(r"^\*生成时间：.*\*$", "*生成时间：<normalized>*", text, flags=re.MULTILINE)
    return re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:[+-]\d{2}:\d{2})?", "<timestamp>", text)


def normalize_output(text: str, work: Path | None = None) -> str:
    """Strip volatile parts (timestamps, run-specific paths) before cross-run hashing."""
    import re

    text = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:[+-]\d{2}:\d{2})?", "<timestamp>", text)
    if work is not None:
        for variant in {str(work), str(work).replace("\\", "/")}:
            text = text.replace(variant, "<work>")
    return text
