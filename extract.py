#!/usr/bin/env python3
"""Snapshot the Open Anesthesia Sim docket for the queue dashboard.

Clones github.com/stuthedew/open-anesthesia-sim into a temporary directory,
reads docs/items/*.md, runs three read-only `bin/docket` commands (digest,
flight, stranded), and writes one JSON file the page reads. Nothing here writes
to the project repository, and the project contains nothing about this one.

Counting rules (they reproduce the 2026-09-13 queue report exactly at 6cd1a1d):
  new      = item whose `added:` date falls in the range
  cleared  = item with status done or dropped whose `closed:` date falls in it
  open     = status untriaged, ready, needs-decision or blocked
  today    = the calendar day in --timezone (default America/Chicago), not UTC
  lane     = every `touches` path under docket.toml workflow_paths -> workflow,
             none -> product, some -> crossing, no touches -> unplaced
             (the same test `docket next` uses, via Item.lane)

Standard library only (Python 3.11+ for tomllib).

    python3 extract.py                        # writes site/data/snapshot.json
    python3 -m http.server -d site 8000       # preview at http://localhost:8000
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

EXTRACTOR_VERSION = 3
# The zone the page calls a "day". Item `added:`/`closed:` are bare calendar
# dates, so the report only reads as one clock if "today" is that same zone
# rather than UTC, which rolls over mid-evening in the US.
DEFAULT_TIMEZONE = "America/Chicago"
REPO_URL = "https://github.com/stuthedew/open-anesthesia-sim"
BASE_REF = "origin/main"

# Mirrors subprojects/docket/src/docket/model.py and store.py, so lanes and
# statuses match the project's own reading without importing its internals.
FRONT_MATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.DOTALL)
FIELD_RE = re.compile(r"^([a-z][a-z0-9-]*):[ \t]*(.*)$")
OPEN_STATUSES = ("untriaged", "ready", "needs-decision", "blocked")
CLOSED_STATUSES = ("done", "dropped")
ID_ALPHABET = "0123456789BCDFGHJKLMNPQRSTVWXYZ"
ID_RE = re.compile(rf"\bPL-(?:[{ID_ALPHABET}]{{4}}|\d{{3}})(?![{ID_ALPHABET}])", re.IGNORECASE)
LANE_CODES = {"product": "p", "workflow": "w", "crossing": "c", "unplaced": "u"}
ITEM_COLUMNS = ["id", "title", "status", "priority", "effort", "lane", "added",
                "closed", "classes", "feature", "pr", "file"]


def git(repo: Path, *args: str, check: bool = True) -> str:
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if check and done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def front_matter(text: str) -> dict[str, str]:
    match = FRONT_MATTER_RE.match(text)
    if match is None:
        return {}
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        field = FIELD_RE.match(line)
        if field:
            fields[field.group(1)] = field.group(2).strip()  # last key wins, as docket does
    return fields


def split_list(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def iso_date(value: str) -> str:
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError:
        return ""


def is_under(path: str, roots: tuple[str, ...]) -> bool:
    candidate = path.strip().strip("/")
    for root in roots:
        target = root.strip().strip("/")
        if target and (candidate == target or candidate.startswith(target + "/")):
            return True
    return False


def lane(touches: list[str], workflow_paths: tuple[str, ...]) -> str:
    if not workflow_paths or not touches:
        return "unplaced"
    inside = [is_under(p, workflow_paths) for p in touches]
    if all(inside):
        return "workflow"
    if not any(inside):
        return "product"
    return "crossing"


def read_items(repo: Path, items_dir: str, workflow_paths: tuple[str, ...]) -> list[list]:
    rows = []
    for path in sorted((repo / items_dir).glob("*.md")):
        if path.name == "README.md":
            continue
        f = front_matter(path.read_text(encoding="utf-8"))
        rows.append([
            f.get("id", ""), f.get("title", ""), f.get("status", ""), f.get("priority", ""),
            f.get("effort", ""),
            LANE_CODES[lane(split_list(f.get("touches", "")), workflow_paths)],
            iso_date(f.get("added", "")), iso_date(f.get("closed", "")),
            split_list(f.get("classes", "")), f.get("feature", ""), f.get("pr", ""), path.name,
        ])
    return rows


def docket(repo: Path, *args: str) -> str:
    """Run a read-only docket command; failure is recorded as empty, never fatal."""
    try:
        done = subprocess.run(["bin/docket", *args], cwd=repo, capture_output=True,
                              text=True, timeout=180)
        return done.stdout if done.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def parse_flight(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        m = re.match(r"^(PL-[0-9A-Z]+)\s+(\S+)\s+(.*)$", line)
        if m:
            out.append({"id": m.group(1), "ref": m.group(2), "note": m.group(3).strip()})
    return out


def parse_stranded(text: str) -> list[dict]:
    out: list[dict] = []
    for line in text.splitlines():
        head = re.match(r"^(PL-[0-9A-Z]+)\s{2,}(.*)$", line)
        if head:
            out.append({"id": head.group(1), "title": head.group(2).strip(), "refs": []})
            continue
        only = re.match(r"^\s+only on:\s*(.*)$", line)
        if only and out:
            out[-1]["refs"] = split_list(only.group(1))
    return out


def branch_facts(repo: Path) -> list[dict]:
    prs: dict[str, list[int]] = {}
    for line in git(repo, "ls-remote", "origin", "refs/pull/*/head", check=False).splitlines():
        sha, _, ref = line.partition("\t")
        if ref.count("/") == 3:
            prs.setdefault(sha, []).append(int(ref.split("/")[2]))
    refs = git(repo, "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin").split()
    out = []
    for ref in refs:
        if ref in ("origin", "origin/HEAD", BASE_REF):
            continue
        tip = git(repo, "rev-parse", ref).strip()
        ahead = int(git(repo, "rev-list", "--count", f"{BASE_REF}..{ref}").strip() or 0)
        behind = int(git(repo, "rev-list", "--count", f"{ref}..{BASE_REF}").strip() or 0)
        when, _, subject = git(repo, "log", "-1", "--format=%cI%x09%s", ref).strip().partition("\t")
        subjects = git(repo, "log", "--no-merges", "--format=%s", f"{BASE_REF}..{ref}").splitlines()
        base = git(repo, "merge-base", BASE_REF, ref, check=False).strip()
        changed = git(repo, "diff", "--name-only", base, ref, check=False).split() if base else []
        ids = sorted({m.upper() for s in [ref, *subjects] for m in ID_RE.findall(s)})
        out.append({
            "ref": ref, "name": ref.removeprefix("origin/"), "tip": tip[:7], "last": when,
            "subject": subjects[0] if subjects else subject, "ahead": ahead, "behind": behind,
            "ids": ids, "files": len(changed),
            "store_only": bool(changed) and all(p.startswith("docs/items/") for p in changed),
            "pr": max(prs.get(tip, [0])) or None,
        })
    return sorted(out, key=lambda b: b["last"], reverse=True)


def snapshot(repo: Path, args: argparse.Namespace) -> dict:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    sha = git(repo, "rev-parse", BASE_REF).strip()
    commit_time, _, commit_subject = git(repo, "log", "-1", "--format=%cI%x09%s", BASE_REF).strip().partition("\t")
    cfg = tomllib.loads((repo / "docket.toml").read_text(encoding="utf-8")).get("docket", {})
    workflow_paths = tuple(cfg.get("workflow_paths", ()))
    rows = read_items(repo, cfg.get("items_dir", "docs/items"), workflow_paths)

    digest = docket(repo, "digest")
    m = re.search(r"Docket:\s+(\d+)\s+open", digest)
    extractor_open = sum(1 for r in rows if r[2] in OPEN_STATUSES)
    run_url = ""
    if os.environ.get("GITHUB_RUN_ID"):
        run_url = (f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/"
                   f"{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ['GITHUB_RUN_ID']}")
    meta = {
        "schema": 2, "extractor_version": EXTRACTOR_VERSION,
        "refresh_id": f"{sha[:7]}-{now.strftime('%Y%m%dT%H%M%SZ')}",
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "interval_minutes": args.interval_minutes,
        "report_timezone": args.timezone,
        "dashboard_repo": args.dashboard_repo, "workflow_file": args.workflow_file,
        "build_run_url": run_url,
        "repo_url": REPO_URL, "base_ref": BASE_REF, "sha": sha,
        "commit_time": commit_time, "commit_subject": commit_subject,
        "item_columns": ITEM_COLUMNS, "item_count": len(rows),
        "workflow_paths_count": len(workflow_paths),
        "check": {"extractor_open": extractor_open,
                  "docket_open": int(m.group(1)) if m else None,
                  "unknown_statuses": sorted({r[2] for r in rows} - set(OPEN_STATUSES) - set(CLOSED_STATUSES))},
        "branches": branch_facts(repo),
        "flight": parse_flight(docket(repo, "flight")),
        "stranded": parse_stranded(docket(repo, "stranded")),
        "digest": digest.strip(),
    }
    return {"meta": meta, "rows": rows}


def check_timezone(name: str) -> None:
    """Fail here on a bad zone name rather than silently in the browser."""
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    except ImportError:  # no tzdata on this machine; the page resolves it anyway
        return
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise SystemExit(f"--timezone {name!r} is not an IANA zone name: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="site/data", help="directory for snapshot.json")
    ap.add_argument("--workdir", default="", help="clone here instead of a temporary directory")
    ap.add_argument("--dashboard-repo", default=os.environ.get("GITHUB_REPOSITORY", ""),
                    help="owner/name of this dashboard repo, for the page's links")
    ap.add_argument("--workflow-file", default="refresh.yml")
    ap.add_argument("--interval-minutes", type=int, default=15,
                    help="the schedule's cadence, so the page knows when data is late")
    ap.add_argument("--timezone", default=os.environ.get("REPORT_TIMEZONE") or DEFAULT_TIMEZONE,
                    help=f"IANA zone the page draws days in (default {DEFAULT_TIMEZONE})")
    args = ap.parse_args()
    check_timezone(args.timezone)

    with tempfile.TemporaryDirectory(prefix="oas-") as tmp:
        repo = Path(args.workdir or Path(tmp) / "open-anesthesia-sim")
        if repo.exists():
            raise SystemExit(f"{repo} already exists; pass an empty --workdir")
        subprocess.run(["git", "clone", "--quiet", REPO_URL + ".git", str(repo)], check=True)
        snap = snapshot(repo, args)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    target, part = out / "snapshot.json", out / "snapshot.json.part"
    part.write_text(json.dumps(snap, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    part.replace(target)  # atomic: a reader never sees half a file

    meta, check = snap["meta"], snap["meta"]["check"]
    ok = check["docket_open"] is None or check["docket_open"] == check["extractor_open"]
    print(f"main {meta['sha'][:7]} ({meta['commit_time']}): {meta['item_count']} items, "
          f"{check['extractor_open']} open; docket digest says {check['docket_open']} "
          f"-> {'match' if ok else 'MISMATCH'}; {len(meta['branches'])} branches, "
          f"{len(meta['flight'])} in flight; wrote {target} ({target.stat().st_size / 1024:.0f} KB)")
    if check["unknown_statuses"]:
        print(f"WARNING: statuses this extractor does not know: {check['unknown_statuses']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
