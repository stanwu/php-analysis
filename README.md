# PHP Analysis

A PHP branch / nesting-complexity analyzer. It parses PHP source code using pure-Python regular expressions, counts `if / elseif / else` branches and nesting depth, and outputs a JSON report—**no PHP runtime or third-party libraries required**.

This repo contains three implementations built by different AI tools so you can compare design trade-offs.

---

## Project Layout

```
php-analysis/
├── .github/                   # GitHub Actions (CI / Release)
├── claude/                    # Claude version (most feature-complete)
│   ├── php_analyzer.py
│   ├── Makefile
│   └── tests/
│       ├── __init__.py
│       └── test_php_analyzer.py
├── codex/                     # Codex version (another full implementation)
│   ├── php_analyzer.py
│   ├── Makefile
│   └── test_php_analyzer.py
├── gemini/                    # Gemini version (minimal implementation)
│   ├── php_analyzer.py
│   ├── Makefile
│   └── test_php_analyzer.py
├── Makefile                   # Root commands (run all tests)
├── README-claude.md           # Details for the claude/ version
├── README-codex.md            # Details for the codex/ version
├── README-gemini.md           # Details for the gemini/ version
└── README.md                  # This file
```

---

## Feature Comparison

| Feature | `claude/` | `codex/` | `gemini/` |
|------|:---------:|:--------:|:---------:|
| String / comment sanitization | ✓ | ✓ | ✗ |
| heredoc / nowdoc handling | ✓ | ✓ | ✗ |
| `#` single-line comments | ✗ | ✓ | ✗ |
| Alternative syntax (`if (...): ... endif;`) | ✗ | ✓ | ✗ |
| Depth calculation | brace + indent | brace (if nesting) | brace only |
| Function grouping | ✓ | ✓ | ✗ |
| `--output` / `--indent` CLI options | ✓ | ✗ | ✗ |
| Timestamp in output (`generated_at`) | ✗ | ✓ | ✗ |
| Unit tests | ✓ (separate `tests/` dir) | ✓ | ✓ |
| ruff lint support | ✓ | ✗ | ✗ |

**Recommended:**

- **Analyzing real-world PHP projects** → use `codex/` or `claude/` (both include full sanitization and function grouping)
- **Quick validation / learning the core logic** → use `gemini/` (the most compact and readable code)

---

## Requirements

- Python 3.8+
- `make` (used to run each version’s Makefile)
- No runtime third-party dependencies
- (Optional) `ruff` for `make lint` in the `claude/` version

Quick install on Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y python3 make
```

---

## Quick Start

### codex/ (recommended)

```bash
make -C codex analyze DIR=/path/to/your/php/project
# Or run directly:
python3 codex/php_analyzer.py /path/to/your/php/project
```

### claude/

```bash
make -C claude run DIR=/path/to/your/php/project
# Or run directly (supports --output / --indent):
python3 claude/php_analyzer.py /path/to/your/php/project \
    --output my_report.json \
    --indent 4
```

| Option | Default | Description |
|------|--------|------|
| `--output` / `-o` | `analysis_report.json` | Path to the JSON report |
| `--indent` | `2` | JSON indentation; `0` for compact output |

### gemini/

```bash
make -C gemini run DIR=/path/to/your/php/project
# Or run directly:
python3 gemini/php_analyzer.py /path/to/your/php/project
```

After running, it writes `analysis_report.json` to the **current working directory** and prints a short summary to stdout.

---

## Running Tests

### Run the full suite (recommended)

From the repo root:

```bash
make test
```

(Optional) Run lint (requires `python3 -m pip install ruff`):

```bash
make lint
```

### Run each version separately

```bash
make -C claude test    # unittest + py_compile
make -C codex  test    # unittest + py_compile
make -C gemini test    # unittest + py_compile
```

Run lint (requires `python3 -m pip install ruff`):

```bash
make -C claude lint
```

---

## CI / CD (GitHub Actions)

- CI: `.github/workflows/ci.yml` (runs on push/PR; multiple Python versions + unit tests + `claude/` lint)
- Release (CD): `.github/workflows/release.yml` (triggers on tags `v*`; runs tests, packages a zip, and creates a GitHub Release with assets)

Example (create a release):

```bash
git tag v1.0.0
git push origin v1.0.0
```

---

## Output Report Format

All versions output similar JSON. The core fields look like this:

```json
{
  "summary": {
    "total_files": 15,
    "total_branches": 87,
    "most_complex": [
      { "file": "src/Controller/OrderController.php", "max_depth": 6, "total_branches": 22 }
    ]
  },
  "files": {
    "src/Controller/OrderController.php": {
      "max_depth": 6,
      "total_branches": 22,
      "branches": [
        { "type": "if",     "line": 42, "depth": 2, "condition": "$order->getStatus() === ''" },
        { "type": "elseif", "line": 45, "depth": 2, "condition": "$order->getStatus() === ''" },
        { "type": "else",   "line": 48, "depth": 2, "condition": "" }
      ],
      "functions": [
        {
          "name": "processOrder",
          "start_line": 38, "end_line": 65,
          "total_branches": 5, "max_depth": 3,
          "branches": ["..."]
        }
      ]
    }
  }
}
```

> **Note:** `claude/` and `codex/` replace string literals with empty placeholders before analysis. As a result, string keys in `condition` (e.g. `$item['type']`) may appear as `$item['']`. This is expected.

---

## Caveats

This is a *best-effort* text scanner, so it may mis-detect in cases like:

- Dynamically constructed PHP code
- Highly irregular indentation or brace formatting
- Huge heredocs / dynamic strings that contain control-flow keywords

If you need 100% accurate AST-based parsing, consider using a full parser such as `nikic/php-parser`.

---

## License

MIT License (see `LICENSE`).
