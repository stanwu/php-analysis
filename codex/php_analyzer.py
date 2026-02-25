#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


KEYWORD_RE = re.compile(r"\b(if|elseif|else|endif)\b", re.IGNORECASE)
FUNCTION_RE = re.compile(
    r"\bfunction\b(?P<ws1>\s+)(?P<ref>&\s*)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)?\s*\(",
    re.IGNORECASE,
)


def _build_line_starts(text: str) -> List[int]:
    line_starts = [0]
    for idx, ch in enumerate(text):
        if ch == "\n":
            line_starts.append(idx + 1)
    return line_starts


def _line_number_at(line_starts: List[int], index: int) -> int:
    return bisect_right(line_starts, index)


def _blank_except_newlines(buf: list[str], start: int, end: int) -> None:
    for i in range(start, end):
        if buf[i] != "\n":
            buf[i] = " "


def sanitize_php(code: str) -> str:
    """
    Returns a same-length string where strings/comments are replaced with spaces
    (newlines preserved). This reduces false-positive keyword matches.
    """
    out = list(code)
    i = 0
    n = len(code)

    while i < n:
        ch = code[i]

        # Single-quoted / double-quoted strings
        if ch in ("'", '"'):
            quote = ch
            start = i
            i += 1
            while i < n:
                if code[i] == "\\":
                    i += 2
                    continue
                if code[i] == quote:
                    i += 1
                    break
                i += 1
            _blank_except_newlines(out, start, min(i, n))
            continue

        # Line comments: //... and #...
        if code.startswith("//", i) or code[i] == "#":
            start = i
            while i < n and code[i] != "\n":
                i += 1
            _blank_except_newlines(out, start, i)
            continue

        # Block comments: /* ... */
        if code.startswith("/*", i):
            start = i
            i += 2
            while i < n and not code.startswith("*/", i):
                i += 1
            i = min(i + 2, n)
            _blank_except_newlines(out, start, i)
            continue

        # Heredoc / nowdoc: <<<IDENT ... IDENT;
        if code.startswith("<<<", i):
            start = i
            j = i + 3
            while j < n and code[j] in " \t":
                j += 1

            ident = ""
            if j < n and code[j] in ("'", '"'):
                q = code[j]
                j += 1
                ident_start = j
                while j < n and code[j] != q:
                    j += 1
                ident = code[ident_start:j]
                j = min(j + 1, n)
            else:
                ident_start = j
                while j < n and (code[j].isalnum() or code[j] == "_"):
                    j += 1
                ident = code[ident_start:j]

            while j < n and code[j] != "\n":
                j += 1
            j = min(j + 1, n)

            end = n
            if ident:
                k = j
                while k < n:
                    line_start = k
                    line_end = code.find("\n", k)
                    if line_end == -1:
                        line_end = n
                    stripped = code[line_start:line_end].strip()
                    if stripped == ident or stripped == f"{ident};":
                        end = line_end
                        if end < n and code[end] == "\n":
                            end += 1
                        break
                    k = line_end + 1

            _blank_except_newlines(out, start, end)
            i = end
            continue

        i += 1

    return "".join(out)


def _skip_ws(text: str, idx: int) -> int:
    n = len(text)
    while idx < n and text[idx].isspace():
        idx += 1
    return idx


def _extract_balanced_parens(text: str, open_paren_idx: int) -> Optional[Tuple[int, int]]:
    """
    Given text[open_paren_idx] == '(' returns (start, end_exclusive) for the
    full balanced parenthetical expression, else None if unbalanced.
    """
    if open_paren_idx < 0 or open_paren_idx >= len(text) or text[open_paren_idx] != "(":
        return None
    depth = 0
    i = open_paren_idx
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return (open_paren_idx, i + 1)
        i += 1
    return None


@dataclass
class BranchBlock:
    type: str  # if / elseif / else
    line: int
    statement_brace_depth: int
    if_nesting_depth: int
    condition: Optional[str] = None
    block_style: str = "none"  # brace / alt / none


@dataclass
class FunctionReport:
    name: str
    start_line: int
    end_line: Optional[int] = None
    total_branches: int = 0
    max_depth: int = 0
    blocks: List[BranchBlock] = field(default_factory=list)


@dataclass
class FileReport:
    max_depth: int = 0
    max_brace_depth: int = 0
    total_branches: int = 0
    blocks: List[BranchBlock] = field(default_factory=list)
    functions: List[FunctionReport] = field(default_factory=list)


def analyze_php_file(path: Path, root: Path) -> Tuple[str, FileReport]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    sanitized = sanitize_php(raw)
    line_starts = _build_line_starts(raw)

    events: List[Tuple[int, str, re.Match]] = []
    for m in KEYWORD_RE.finditer(sanitized):
        events.append((m.start(), "kw", m))
    for m in FUNCTION_RE.finditer(sanitized):
        events.append((m.start(), "fn", m))
    events.sort(key=lambda x: x[0])

    report = FileReport()
    brace_depth = 0

    # Tracks active if-block nesting only (not all braces). Two forms:
    # - brace-based: start_level is the brace depth inside the if body
    # - alt-based: popped by encountering "endif"
    if_brace_stack: List[int] = []
    if_alt_stack: List[None] = []

    function_stack: List[Tuple[int, FunctionReport]] = []  # (start_level, report)

    def current_function() -> Optional[FunctionReport]:
        return function_stack[-1][1] if function_stack else None

    pending_function: Optional[FunctionReport] = None
    pending_function_brace_pos: Optional[int] = None

    pending_if_push: Optional[Tuple[str, int]] = None  # (kind, expected_open_pos)

    def snapshot_if_nesting_depth() -> int:
        return len(if_brace_stack) + len(if_alt_stack)

    pos = 0
    for event_pos, event_kind, match in events + [(len(sanitized), "eof", None)]:  # type: ignore[list-item]
        # Advance through text updating brace depth and popping stacks.
        while pos < event_pos:
            ch = sanitized[pos]

            if ch == "{":
                brace_depth += 1
                report.max_brace_depth = max(report.max_brace_depth, brace_depth)

                # Start a pending function body if its opening brace is here.
                if pending_function is not None and pending_function_brace_pos == pos:
                    function_stack.append((brace_depth, pending_function))
                    report.functions.append(pending_function)
                    pending_function = None
                    pending_function_brace_pos = None

                # Start a pending if body if its opening brace is here.
                if pending_if_push is not None and pending_if_push[1] == pos:
                    if_brace_stack.append(brace_depth)
                    report.max_depth = max(report.max_depth, snapshot_if_nesting_depth())
                    cur_fn = current_function()
                    if cur_fn is not None:
                        cur_fn.max_depth = max(cur_fn.max_depth, snapshot_if_nesting_depth())
                    pending_if_push = None

            elif ch == "}":
                brace_depth = max(brace_depth - 1, 0)

                # Pop any if blocks that ended at this brace depth.
                while if_brace_stack and if_brace_stack[-1] > brace_depth:
                    if_brace_stack.pop()

                # Pop any function blocks that ended at this brace depth.
                while function_stack and function_stack[-1][0] > brace_depth:
                    start_level, fnr = function_stack.pop()
                    fnr.end_line = _line_number_at(line_starts, pos)

            pos += 1

        if event_kind == "eof":
            break

        if event_kind == "fn":
            name = match.group("name") if match is not None else None
            line = _line_number_at(line_starts, event_pos)
            if not name:
                name = f"<anonymous@L{line}>"

            # Find the opening brace for the function body (if any).
            j = _skip_ws(sanitized, match.end() if match is not None else event_pos)
            # Move forward until we hit '{' or ';' at the same level (approx).
            # This is intentionally shallow: it avoids deep parsing but keeps a useful function grouping.
            scan = j
            n = len(sanitized)
            open_brace_pos = None
            while scan < n:
                c = sanitized[scan]
                if c == "{":
                    open_brace_pos = scan
                    break
                if c == ";":
                    break
                if scan - event_pos > 20000:
                    break
                scan += 1

            if open_brace_pos is not None:
                pending_function = FunctionReport(name=name, start_line=line)
                pending_function_brace_pos = open_brace_pos

        if event_kind == "kw":
            kw = match.group(1).lower()  # type: ignore[union-attr]
            line = _line_number_at(line_starts, event_pos)
            statement_brace_depth = brace_depth

            if kw == "endif":
                if if_alt_stack:
                    if_alt_stack.pop()
                continue

            cond: Optional[str] = None
            block_style = "none"
            expected_open_pos: Optional[int] = None
            opens_alt = False

            if kw in ("if", "elseif"):
                j = _skip_ws(sanitized, match.end())  # type: ignore[union-attr]
                if j < len(sanitized) and sanitized[j] == "(":
                    par = _extract_balanced_parens(sanitized, j)
                    if par is not None:
                        cond = raw[par[0] + 1 : par[1] - 1].strip()
                        j = _skip_ws(sanitized, par[1])
                        if j < len(sanitized):
                            if sanitized[j] == "{":
                                block_style = "brace"
                                expected_open_pos = j
                            elif sanitized[j] == ":":
                                block_style = "alt"
                                opens_alt = True
            else:  # else
                j = _skip_ws(sanitized, match.end())  # type: ignore[union-attr]
                if j < len(sanitized):
                    if sanitized[j] == "{":
                        block_style = "brace"
                        expected_open_pos = j
                    elif sanitized[j] == ":":
                        block_style = "alt"
                        opens_alt = True

            # Nesting depth at the statement location (if nesting only).
            # For "if", the nesting increases only when its body starts (brace/alt).
            current_if_depth = snapshot_if_nesting_depth()
            if kw == "if" and block_style in ("brace", "alt"):
                stmt_if_nesting = current_if_depth + 1
            else:
                stmt_if_nesting = current_if_depth

            block = BranchBlock(
                type=kw,
                line=line,
                statement_brace_depth=statement_brace_depth,
                if_nesting_depth=stmt_if_nesting,
                condition=cond,
                block_style=block_style,
            )
            report.blocks.append(block)
            report.total_branches += 1

            fnr = current_function()
            if fnr is not None:
                fnr.blocks.append(block)
                fnr.total_branches += 1

            if kw == "if":
                if block_style == "brace" and expected_open_pos is not None:
                    pending_if_push = ("brace", expected_open_pos)
                    report.max_depth = max(report.max_depth, current_if_depth + 1)
                    if fnr is not None:
                        fnr.max_depth = max(fnr.max_depth, current_if_depth + 1)
                elif block_style == "alt" and opens_alt:
                    if_alt_stack.append(None)
                    report.max_depth = max(report.max_depth, snapshot_if_nesting_depth())
                    if fnr is not None:
                        fnr.max_depth = max(fnr.max_depth, snapshot_if_nesting_depth())

    rel = str(path.relative_to(root)).replace(os.sep, "/")
    return rel, report


def _to_jsonable(obj):
    if isinstance(obj, list):
        return [_to_jsonable(x) for x in obj]
    if hasattr(obj, "__dataclass_fields__"):
        d = {}
        for k in obj.__dataclass_fields__.keys():  # type: ignore[attr-defined]
            d[k] = _to_jsonable(getattr(obj, k))
        return d
    return obj


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Regex-based PHP if/elseif/else analyzer.")
    parser.add_argument("directory", help="Root directory to scan for .php files")
    args = parser.parse_args(argv)

    root = Path(args.directory).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2

    php_files: List[Path] = []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.lower().endswith(".php"):
                php_files.append(Path(dirpath) / fn)
    php_files.sort()

    files_report: Dict[str, Dict[str, Any]] = {}
    total_branches = 0

    complexity_rows: List[Tuple[int, str, int]] = []  # (max_depth, path, branches)

    for php_path in php_files:
        rel, rep = analyze_php_file(php_path, root)
        files_report[rel] = _to_jsonable(rep)
        total_branches += rep.total_branches
        complexity_rows.append((rep.max_depth, rel, rep.total_branches))

    complexity_rows.sort(key=lambda x: (x[0], x[2], x[1]), reverse=True)
    most_complex = [
        {"path": p, "max_depth": d, "total_branches": b} for d, p, b in complexity_rows[:10]
    ]

    report = {
        "summary": {
            "root": str(root),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_files": len(php_files),
            "total_branches": total_branches,
            "most_complex": most_complex,
        },
        "files": files_report,
    }

    out_path = Path("analysis_report.json").resolve()
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Terminal summary
    print(f"Total files scanned: {len(php_files)}")
    print(f"Total branches: {total_branches}")
    print("\nTop 10 most complex files (by max if-nesting depth):")
    for depth, rel, branches in complexity_rows[:10]:
        print(f"  depth={depth:>3} branches={branches:>4}  {rel}")

    print("\nTotal branch count per file:")
    for depth, rel, branches in sorted(complexity_rows, key=lambda x: (x[2], x[0], x[1]), reverse=True):
        print(f"  branches={branches:>4} depth={depth:>3}  {rel}")

    print(f"\nWrote JSON report: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
