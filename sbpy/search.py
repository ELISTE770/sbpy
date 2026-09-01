"""חיפוש סמנטי בקוד (Semantic Code Search).

מאפשר לשאול שאלות בשפה חופשית ("איפה מטפלים בשגיאות חיבור?", "מציאת מנגנון קאש")
ולאתר את הפונקציות, המחלקות והרכיבים הרלוונטיים ביותר בארכיטקטורת הפרויקט.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any

from .config import TIER_COMMAND, Config, get_config
from .console import Console, get_console
from .gemini import get_engine
from .spinner import Spinner


@dataclass
class SearchResult:
    file: str
    line: int
    symbol: str
    kind: str
    snippet: str
    score: float = 0.8
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "symbol": self.symbol,
            "kind": self.kind,
            "snippet": self.snippet,
            "score": self.score,
            "reason": self.reason,
        }


def _extract_symbols_from_file(file_path: str) -> list[dict[str, Any]]:
    """מחלץ מחלקות, פונקציות ותיעוד מקובץ פייתון באמצעות AST."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except OSError:
        return []

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError:
        return []

    symbols: list[dict[str, Any]] = []
    lines = source.splitlines()

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node) or ""
            start = node.lineno
            end = getattr(node, "end_lineno", start + 5)
            snippet = "\n".join(lines[start - 1 : min(end, start + 8)])
            symbols.append({
                "name": node.name,
                "kind": "function",
                "line": node.lineno,
                "doc": doc,
                "snippet": snippet,
                "file": file_path,
            })
        elif isinstance(node, ast.ClassDef):
            doc = ast.get_docstring(node) or ""
            start = node.lineno
            end = getattr(node, "end_lineno", start + 5)
            snippet = "\n".join(lines[start - 1 : min(end, start + 8)])
            symbols.append({
                "name": node.name,
                "kind": "class",
                "line": node.lineno,
                "doc": doc,
                "snippet": snippet,
                "file": file_path,
            })
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    sub_doc = ast.get_docstring(sub) or ""
                    sub_start = sub.lineno
                    sub_end = getattr(sub, "end_lineno", sub_start + 5)
                    sub_snippet = "\n".join(lines[sub_start - 1 : min(sub_end, sub_start + 8)])
                    symbols.append({
                        "name": f"{node.name}.{sub.name}",
                        "kind": "method",
                        "line": sub.lineno,
                        "doc": sub_doc,
                        "snippet": sub_snippet,
                        "file": file_path,
                    })

    return symbols


def semantic_code_search(
    query: str,
    root_dir: str = ".",
    max_results: int = 5,
    config: Config | None = None,
) -> list[SearchResult]:
    """מבצע חיפוש סמנטי על כלל סמלי הפרויקט באמצעות AST ו-AI."""
    config = config or get_config()
    all_symbols: list[dict[str, Any]] = []

    # Traverse directory
    from .cli import iter_python_files

    for fpath in iter_python_files(root_dir):
        all_symbols.extend(_extract_symbols_from_file(fpath))

    if not all_symbols:
        return []

    # Lexical pre-filter
    keywords = re.findall(r"\w+", query.lower())
    scored_candidates: list[tuple[float, dict[str, Any]]] = []

    for sym in all_symbols:
        text = f"{sym['name']} {sym['doc']} {sym['snippet']}".lower()
        match_count = sum(1 for kw in keywords if kw in text)
        score = match_count / max(1, len(keywords))
        scored_candidates.append((score, sym))

    scored_candidates.sort(key=lambda x: x[0], reverse=True)
    top_candidates = [c[1] for c in scored_candidates[:20]]

    # If offline or no AI, return top lexical matches
    if config.offline or not top_candidates:
        results: list[SearchResult] = []
        for sym in top_candidates[:max_results]:
            results.append(
                SearchResult(
                    file=sym["file"],
                    line=sym["line"],
                    symbol=sym["name"],
                    kind=sym["kind"],
                    snippet=sym["snippet"],
                    score=0.7,
                    reason=f"Matches keywords in {sym['name']}",
                )
            )
        return results

    # Ask AI engine to rank and explain relevance
    symbols_text = "\n\n".join(
        f"ID: {i}\nSymbol: {s['name']} ({s['kind']}) in {s['file']}:{s['line']}\nDocstring: {s['doc']}\nCode:\n{s['snippet']}"
        for i, s in enumerate(top_candidates[:12])
    )

    prompt = f"""You are SBpy's Semantic Code Search Engine.
USER QUERY: "{query}"

CANDIDATE CODE SYMBOLS:
{symbols_text}

Identify the top {max_results} most relevant symbols answering the user query.
Respond ONLY with a JSON list in the following format:
[
  {{
    "id": 0,
    "score": 0.95,
    "reason": "Explains why this symbol is relevant"
  }}
]
"""
    engine = get_engine(config)
    with Spinner("Semantic Search analyzing codebase..."):
        resp = engine.generate(prompt, tier=TIER_COMMAND)

    results = []
    if resp.ok and resp.data and isinstance(resp.data, list):
        for item in resp.data:
            if isinstance(item, dict) and "id" in item:
                idx = item["id"]
                if 0 <= idx < len(top_candidates):
                    sym = top_candidates[idx]
                    results.append(
                        SearchResult(
                            file=sym["file"],
                            line=sym["line"],
                            symbol=sym["name"],
                            kind=sym["kind"],
                            snippet=sym["snippet"],
                            score=float(item.get("score", 0.8)),
                            reason=str(item.get("reason", "")),
                        )
                    )

    if not results:
        # Fallback to top lexical
        for sym in top_candidates[:max_results]:
            results.append(
                SearchResult(
                    file=sym["file"],
                    line=sym["line"],
                    symbol=sym["name"],
                    kind=sym["kind"],
                    snippet=sym["snippet"],
                    score=0.7,
                    reason="Matched code structure and symbols",
                )
            )

    return results


def render_search_results(
    results: list[SearchResult],
    query: str,
    console: Console | None = None,
) -> None:
    """מדפיס תוצאות חיפוש סמנטי מעוצבות לטרמינל."""
    console = console or get_console()

    console.write(console.paint(f"\n  🔍 Semantic Code Search: \"{query}\"", "cyan", bold=True))
    console.write(console.paint(f"  Found {len(results)} relevant symbol(s):\n", "grey"))

    if not results:
        console.write(console.paint("  No matching code symbols found.", "yellow"))
        return

    for i, r in enumerate(results, 1):
        pct = int(r.score * 100)
        console.write(console.paint(f"  [{i}] {r.symbol} ({r.kind})", "green", bold=True) + console.paint(f" · {r.file}:{r.line} ({pct}% match)", "grey"))
        if r.reason:
            console.write(console.paint(f"      💡 {r.reason}", "white"))
        # Show first 3 lines of snippet
        snip_lines = r.snippet.splitlines()[:3]
        for line in snip_lines:
            console.write(console.paint(f"        {line}", "grey"))
        console.write("")
