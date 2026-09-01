"""Caching and parallelism for the static pass.

The local layer keeps growing - dozens of rules, plus project-wide graphs.
Two cheap wins keep it fast:

* **Cache** - a file that has not changed produces the same findings, so
  re-analysing it is pure waste. Keyed by path + mtime + size + a ruleset
  fingerprint, which means a rule change invalidates everything at once.
* **Parallelism** - AST parsing is CPU-bound and independent per file, so
  a process pool turns a long scan into a short one on any modern machine.

Both are transparent: turn them off and behaviour is identical, only slower.
"""

from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from typing import Sequence

from .config import Config, get_config
from .results import Finding
from .static.checks import RULE_CATEGORY, SourceUnit, analyze

# Bump when a rule changes in a way that alters its output for unchanged code.
CACHE_FORMAT = 2

# Measured on this project (49 files): serial 3.1s, pool 5.0s. Windows uses
# `spawn`, so every worker re-imports the whole package - that start-up cost
# only pays off on a big tree. `fork` platforms pay far less, so the default
# differs by platform and the threshold is deliberately high.
PARALLEL_THRESHOLD = 150 if os.name == "nt" else 40
MAX_WORKERS = 8

_ruleset_fingerprint: str | None = None


def ruleset_fingerprint() -> str:
    """A short hash of the active rule set.

    Adding, renaming, or recategorising a rule changes this, which retires
    every cached result - exactly what should happen.
    """
    global _ruleset_fingerprint
    if _ruleset_fingerprint is None:
        payload = json.dumps(
            {"format": CACHE_FORMAT, "rules": sorted(RULE_CATEGORY.items())},
            ensure_ascii=False,
            sort_keys=True,
        )
        _ruleset_fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    return _ruleset_fingerprint


def _key(path: str, categories: Sequence[str]) -> str:
    try:
        stat = os.stat(path)
        stamp = f"{stat.st_mtime_ns}:{stat.st_size}"
    except OSError:
        stamp = "missing"
    raw = "|".join(
        [os.path.abspath(path), stamp, ",".join(sorted(categories)), ruleset_fingerprint()]
    )
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:32]


def _cache_dir(config: Config) -> str:
    directory = config.home / "scans"
    directory.mkdir(parents=True, exist_ok=True)
    return str(directory)


def _load(path: str, categories: Sequence[str], config: Config) -> list[Finding] | None:
    try:
        cache_file = os.path.join(_cache_dir(config), _key(path, categories) + ".json")
        if not os.path.exists(cache_file):
            return None
        with open(cache_file, "r", encoding="utf-8") as handle:
            rows = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(rows, list):
        return None
    try:
        return [Finding(**row) for row in rows]
    except TypeError:
        # The Finding shape changed - treat the entry as stale.
        return None


def _store(path: str, categories: Sequence[str], config: Config, findings: list[Finding]) -> None:
    try:
        cache_file = os.path.join(_cache_dir(config), _key(path, categories) + ".json")
        temporary = cache_file + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump([asdict(finding) for finding in findings], handle, ensure_ascii=False)
        os.replace(temporary, cache_file)
    except (OSError, TypeError, ValueError):
        return


def analyze_file(path: str, categories: Sequence[str]) -> list[Finding]:
    """The uncached, single-file analysis. Must stay picklable for the pool."""
    try:
        unit = SourceUnit.from_path(path)
    except OSError:
        return []
    if unit.tree is None:
        return []
    return analyze(unit, list(categories))


def _worker(job: tuple[str, tuple[str, ...]]) -> tuple[str, list[Finding]]:
    path, categories = job
    return path, analyze_file(path, categories)


def cached_analyze(
    path: str, categories: Sequence[str], config: Config | None = None
) -> list[Finding]:
    """Analyses one file, reusing the cached result when it is still valid."""
    config = config or get_config()
    if not config.scan_cache:
        return analyze_file(path, categories)

    cached = _load(path, categories, config)
    if cached is not None:
        return cached
    findings = analyze_file(path, categories)
    _store(path, categories, config, findings)
    return findings


def analyze_many(
    paths: Sequence[str],
    categories: Sequence[str],
    config: Config | None = None,
) -> dict[str, list[Finding]]:
    """Analyses many files, using the cache and a process pool when it pays."""
    config = config or get_config()
    categories = tuple(categories)
    results: dict[str, list[Finding]] = {}

    pending: list[str] = []
    for path in paths:
        if config.scan_cache:
            cached = _load(path, categories, config)
            if cached is not None:
                results[path] = cached
                continue
        pending.append(path)

    if not pending:
        return results

    workers = min(MAX_WORKERS, (os.cpu_count() or 2))
    if not config.parallel_scan or len(pending) < PARALLEL_THRESHOLD or workers < 2:
        for path in pending:
            findings = analyze_file(path, categories)
            results[path] = findings
            if config.scan_cache:
                _store(path, categories, config, findings)
        return results

    try:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for path, findings in pool.map(_worker, [(p, categories) for p in pending]):
                results[path] = findings
                if config.scan_cache:
                    _store(path, categories, config, findings)
    except Exception:  # sbpy: ignore=silent-except
        # A pool can fail for reasons unrelated to the code being scanned
        # (spawn restrictions, frozen apps, no __main__). Never lose the scan.
        for path in pending:
            findings = analyze_file(path, categories)
            results[path] = findings
            if config.scan_cache:
                _store(path, categories, config, findings)
    return results


def clear(config: Config | None = None) -> int:
    """Empties the scan cache. Returns how many entries were removed."""
    config = config or get_config()
    directory = config.home / "scans"
    removed = 0
    if directory.exists():
        for entry in directory.glob("*.json"):
            entry.unlink(missing_ok=True)
            removed += 1
    return removed


def stats(config: Config | None = None) -> dict[str, object]:
    config = config or get_config()
    directory = config.home / "scans"
    entries = 0
    size = 0
    if directory.exists():
        for entry in directory.glob("*.json"):
            entries += 1
            try:
                size += entry.stat().st_size
            except OSError:
                continue
    return {
        "entries": entries,
        "bytes": size,
        "directory": str(directory),
        "ruleset": ruleset_fingerprint(),
    }
