#!/usr/bin/env python3
"""
PHP Branch Complexity Analyzer
Recursively scans PHP files and extracts if/elseif/else branch structures,
nesting depths, and condition expressions using regex-based parsing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Strip single-line comments (//) and multi-line comments (/* … */)
_RE_SL_COMMENT  = re.compile(r'//[^\n]*')
_RE_ML_COMMENT  = re.compile(r'/\*.*?\*/', re.DOTALL)
# Strip string literals (basic – avoids matching keywords inside strings)
_RE_DQ_STRING   = re.compile(r'"(?:[^"\\]|\\.)*"', re.DOTALL)
_RE_SQ_STRING   = re.compile(r"'(?:[^'\\]|\\.)*'", re.DOTALL)
_RE_HEREDOC     = re.compile(r'<<<\s*([A-Za-z_]\w*)\n.*?\n\1;', re.DOTALL)
_RE_NOWDOC      = re.compile(r"<<<\s*'([A-Za-z_]\w*)'\n.*?\n\1;", re.DOTALL)

# Branch keyword detection (after stripping strings/comments)
# Matches:  if (   elseif (   else if (   else {  or bare else\n
_RE_IF         = re.compile(r'\bif\s*\(')
_RE_ELSEIF     = re.compile(r'\belseif\s*\(|\belse\s+if\s*\(')
_RE_ELSE       = re.compile(r'\belse\s*(?:\{|//|/\*|$)')   # else not followed by 'if'

# Used to find the parenthesised condition after if/elseif
_RE_CONDITION  = re.compile(r'\b(?:else\s+)?if\s*(\()', re.MULTILINE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_noise(source: str) -> str:
    """Remove strings and comments so keywords inside them are ignored."""
    source = _RE_NOWDOC.sub('""', source)
    source = _RE_HEREDOC.sub('""', source)
    source = _RE_ML_COMMENT.sub('', source)
    source = _RE_SL_COMMENT.sub('', source)
    source = _RE_DQ_STRING.sub('""', source)
    source = _RE_SQ_STRING.sub("''", source)
    return source


def _extract_balanced(text: str, start: int) -> str:
    """
    Given that text[start] == '(', walk forward balancing parens and
    return the inner content (excluding the outer parens).
    """
    depth = 0
    i = start
    while i < len(text):
        if text[i] == '(':
            depth += 1
        elif text[i] == ')':
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
        i += 1
    return text[start + 1:]   # unbalanced – return rest


def _line_of(text: str, pos: int) -> int:
    """Return 1-based line number for character position *pos* in *text*."""
    return text.count('\n', 0, pos) + 1


def _brace_depth_at(text: str, pos: int) -> int:
    """
    Count net open-brace depth up to (but not including) *pos*.
    Braces inside strings/comments have already been stripped.
    """
    return text[:pos].count('{') - text[:pos].count('}')


def _indent_depth_at(original: str, line_no: int) -> int:
    """
    Fallback depth estimate: count leading spaces/tabs on the given line
    and convert to a normalised level (4 spaces or 1 tab = 1 level).
    """
    lines = original.splitlines()
    if line_no < 1 or line_no > len(lines):
        return 0
    line = lines[line_no - 1]
    stripped = line.lstrip()
    indent = len(line) - len(stripped)
    tabs = line[:indent].count('\t')
    spaces = indent - tabs
    return tabs + spaces // 4


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def _analyse_file(path: Path) -> dict:
    """Parse a single PHP file and return its branch analysis."""
    try:
        raw = path.read_bytes()
        original = raw.decode('utf-8', errors='replace')
    except OSError as exc:
        return {"error": str(exc), "checksum": "", "max_depth": 0, "total_branches": 0, "branches": []}

    checksum = hashlib.sha256(raw).hexdigest()

    clean = _strip_noise(original)

    branches: list[dict] = []

    # --- Walk character by character to find branch keywords --------------------
    i = 0
    n = len(clean)

    while i < n:
        # Try to match 'if' or 'elseif' / 'else if'
        m_elseif = _RE_ELSEIF.match(clean, i)
        m_if     = _RE_IF.match(clean, i)       # catches both if and elseif prefix
        m_else   = _RE_ELSE.match(clean, i)

        # Priority: elseif before if (elseif starts with 'else')
        if m_elseif:
            keyword = 'elseif'
            match   = m_elseif
        elif m_if and not (i >= 4 and clean[i-4:i] in ('else', 'lsei')):
            # plain 'if' – but guard against matching 'if' inside 'elseif'
            keyword = 'if'
            match   = m_if
        elif m_else:
            keyword = 'else'
            match   = m_else
        else:
            i += 1
            continue

        word_start = i
        line_no    = _line_of(original, word_start)
        brace_depth = _brace_depth_at(clean, word_start)
        indent_depth = _indent_depth_at(original, line_no)
        depth = max(brace_depth, indent_depth)

        # Extract condition for if/elseif
        condition = ''
        if keyword in ('if', 'elseif'):
            # find the opening paren
            paren_pos = clean.find('(', word_start + len(match.group(0)) - 1)
            if paren_pos != -1:
                condition = _extract_balanced(clean, paren_pos).strip()
                # Collapse whitespace
                condition = re.sub(r'\s+', ' ', condition)

        branches.append({
            "type"     : keyword,
            "line"     : line_no,
            "depth"    : depth,
            "condition": condition,
        })

        i = word_start + len(match.group(0))

    # --- Aggregate per-function grouping  (best-effort via regex) ---------------
    functions = _group_by_function(original, clean, branches)

    max_depth = max((b['depth'] for b in branches), default=0)

    return {
        "checksum"      : checksum,
        "max_depth"     : max_depth,
        "total_branches": len(branches),
        "branches"      : branches,
        "functions"     : functions,
    }


def _group_by_function(original: str, clean: str, branches: list[dict]) -> list[dict]:
    """
    Best-effort grouping: find function/method declarations and assign
    branches that fall within their brace span.
    """
    _RE_FUNC = re.compile(
        r'\b(?:(?:public|protected|private|static|abstract|final)\s+)*'
        r'function\s+(&?\s*\w+)\s*\(',
        re.MULTILINE,
    )

    func_spans: list[tuple[str, int, int]] = []  # (name, start_line, end_line)
    total_lines = original.count('\n') + 1

    func_matches = list(_RE_FUNC.finditer(clean))
    for idx, fm in enumerate(func_matches):
        func_name  = fm.group(1).strip()
        func_start = _line_of(original, fm.start())
        # find opening brace of the function body
        brace_pos  = clean.find('{', fm.end())
        if brace_pos == -1:
            continue
        # walk to matching close brace
        depth = 0
        j = brace_pos
        while j < len(clean):
            if clean[j] == '{':
                depth += 1
            elif clean[j] == '}':
                depth -= 1
                if depth == 0:
                    func_end = _line_of(original, j)
                    func_spans.append((func_name, func_start, func_end))
                    break
            j += 1

    # Assign branches to functions
    func_branches: dict[str, list[dict]] = {}
    unassigned: list[dict] = []

    for branch in branches:
        assigned = False
        for (fname, fstart, fend) in func_spans:
            if fstart <= branch['line'] <= fend:
                func_branches.setdefault(fname, []).append(branch)
                assigned = True
                break
        if not assigned:
            unassigned.append(branch)

    result: list[dict] = []
    for (fname, fstart, fend) in func_spans:
        fb = func_branches.get(fname, [])
        result.append({
            "name"          : fname,
            "start_line"    : fstart,
            "end_line"      : fend,
            "total_branches": len(fb),
            "max_depth"     : max((b['depth'] for b in fb), default=0),
            "branches"      : fb,
        })

    if unassigned:
        result.append({
            "name"          : "<global>",
            "start_line"    : 1,
            "end_line"      : total_lines,
            "total_branches": len(unassigned),
            "max_depth"     : max((b['depth'] for b in unassigned), default=0),
            "branches"      : unassigned,
        })

    return result


# ---------------------------------------------------------------------------
# Directory walker
# ---------------------------------------------------------------------------

def analyse_directory(root: Path) -> dict:
    """Walk *root* recursively, analyse every .php file, return full report."""
    php_files = sorted(root.rglob('*.php'))

    files_report: dict[str, dict] = {}
    total_branches = 0

    for php_path in php_files:
        rel = str(php_path.relative_to(root))
        print(f"  Scanning {rel} …", end='\r', flush=True)
        result = _analyse_file(php_path)
        files_report[rel] = result
        total_branches += result.get('total_branches', 0)

    print(' ' * 80, end='\r')   # clear progress line

    # Detect duplicate files by checksum
    checksum_map: dict[str, list[str]] = {}
    for rel, data in files_report.items():
        cs = data.get('checksum', '')
        if cs:
            checksum_map.setdefault(cs, []).append(rel)
    duplicates = {cs: paths for cs, paths in checksum_map.items() if len(paths) > 1}

    # Build most-complex list
    ranked = sorted(
        files_report.items(),
        key=lambda kv: (kv[1].get('max_depth', 0), kv[1].get('total_branches', 0)),
        reverse=True,
    )[:10]

    most_complex = [
        {
            "file"          : rel,
            "max_depth"     : data.get('max_depth', 0),
            "total_branches": data.get('total_branches', 0),
        }
        for rel, data in ranked
    ]

    return {
        "summary": {
            "total_files"   : len(php_files),
            "total_branches": total_branches,
            "most_complex"  : most_complex,
            "duplicates"    : duplicates,
        },
        "files": files_report,
    }


# ---------------------------------------------------------------------------
# Terminal summary
# ---------------------------------------------------------------------------

def print_summary(report: dict) -> None:
    summary = report['summary']
    files   = report['files']

    print()
    print('=' * 60)
    print('  PHP Branch Complexity Analysis')
    print('=' * 60)
    print(f"  Total files scanned : {summary['total_files']}")
    print(f"  Total branches found: {summary['total_branches']}")
    print()
    print('  Top 10 most complex files (by max nesting depth):')
    print('  ' + '-' * 56)

    header = f"  {'File':<40} {'MaxDepth':>8} {'Branches':>8}"
    print(header)
    print('  ' + '-' * 56)

    for entry in summary['most_complex']:
        fname = entry['file']
        # Truncate long paths for display
        if len(fname) > 40:
            fname = '…' + fname[-(39):]
        print(f"  {fname:<40} {entry['max_depth']:>8} {entry['total_branches']:>8}")

    print()
    print('  Branch count per file:')
    print('  ' + '-' * 56)

    per_file = sorted(
        files.items(),
        key=lambda kv: kv[1].get('total_branches', 0),
        reverse=True,
    )
    for rel, data in per_file:
        fname = rel
        if len(fname) > 40:
            fname = '…' + fname[-39:]
        branches = data.get('total_branches', 0)
        depth    = data.get('max_depth', 0)
        print(f"  {fname:<40} {branches:>5} branches  depth {depth}")

    duplicates = summary.get('duplicates', {})
    if duplicates:
        print()
        print('  Duplicate files (identical checksum):')
        print('  ' + '-' * 56)
        for cs, paths in duplicates.items():
            print(f"  SHA256: {cs[:16]}…")
            for p in paths:
                print(f"    - {p}")
        print()

    print('=' * 60)
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Analyse PHP files for if/elseif/else branch complexity.',
    )
    parser.add_argument(
        'directory',
        help='Root directory to scan recursively for .php files.',
    )
    parser.add_argument(
        '--output', '-o',
        default='analysis_report.json',
        help='Output JSON file path (default: analysis_report.json).',
    )
    parser.add_argument(
        '--indent',
        type=int,
        default=2,
        help='JSON indentation level (default: 2). Use 0 for compact output.',
    )
    args = parser.parse_args()

    root = Path(args.directory)
    if not root.is_dir():
        print(f"Error: '{root}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning PHP files under: {root.resolve()}")
    report = analyse_directory(root)

    indent = args.indent if args.indent > 0 else None
    out_path = Path(args.output)
    out_path.write_text(
        json.dumps(report, indent=indent, ensure_ascii=False),
        encoding='utf-8',
    )
    print(f"JSON report written to: {out_path.resolve()}")

    print_summary(report)


if __name__ == '__main__':
    main()
