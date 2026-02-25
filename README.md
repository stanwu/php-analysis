# PHP_Phraser

PHP 分支/巢狀複雜度分析器。以純 Python 正規表示式解析 PHP 程式碼，統計 `if / elseif / else` 分支數量與巢狀深度，輸出 JSON 報表，**不需要安裝 PHP 或任何第三方函式庫**。

本 repo 收錄三個由不同 AI 工具各自實作的版本，可互相比較設計取捨。

---

## 專案結構

```
PHP_Phraser/
├── .github/                   # GitHub Actions（CI / Release）
├── claude/                    # Claude 版本（功能最完整）
│   ├── php_analyzer.py
│   ├── Makefile
│   └── tests/
│       ├── __init__.py
│       └── test_php_analyzer.py
├── codex/                     # Codex 版本（另一完整實作）
│   ├── php_analyzer.py
│   ├── Makefile
│   └── test_php_analyzer.py
├── gemini/                    # Gemini 版本（精簡實作）
│   ├── php_analyzer.py
│   ├── Makefile
│   └── test_php_analyzer.py
├── Makefile                   # 專案 root 指令（一次跑完所有測試）
├── README-claude.md           # claude/ 版本詳細說明
├── README-codex.md            # codex/ 版本詳細說明
├── README-gemini.md           # gemini/ 版本詳細說明
└── README.md                  # 本文件
```

---

## 版本比較

| 特性 | `claude/` | `codex/` | `gemini/` |
|------|:---------:|:--------:|:---------:|
| 字串 / 註解消毒 | ✓ | ✓ | ✗ |
| heredoc / nowdoc 處理 | ✓ | ✓ | ✗ |
| `#` 單行注解 | ✗ | ✓ | ✗ |
| Alternative syntax（`if (...): ... endif;`）| ✗ | ✓ | ✗ |
| 深度計算 | brace + indent | brace（if 巢狀） | 僅 brace |
| 函式分組 | ✓ | ✓ | ✗ |
| `--output` / `--indent` CLI 選項 | ✓ | ✗ | ✗ |
| 產生時間戳記（`generated_at`）| ✗ | ✓ | ✗ |
| 單元測試 | ✓（獨立 `tests/` 目錄） | ✓ | ✓ |
| ruff lint 支援 | ✓ | ✗ | ✗ |

**建議選擇：**

- **分析真實 PHP 專案** → 使用 `codex/` 或 `claude/`，兩者均有完整的原始碼消毒與函式分組
- **快速驗證 / 學習核心邏輯** → 使用 `gemini/`，程式碼最為精簡易讀

---

## 需求

- Python 3.8+
- `make`（用於執行各版本的 Makefile）
- 無執行期第三方依賴
- （選用）`ruff`：供 `claude/` 版本的 `make lint` 使用

Ubuntu/Debian 快速安裝：

```bash
sudo apt update
sudo apt install -y python3 make
```

---

## 快速開始

### codex/（推薦）

```bash
make -C codex analyze DIR=/path/to/your/php/project
# 或直接執行：
python3 codex/php_analyzer.py /path/to/your/php/project
```

### claude/

```bash
make -C claude run DIR=/path/to/your/php/project
# 或直接執行（支援 --output / --indent）：
python3 claude/php_analyzer.py /path/to/your/php/project \
    --output my_report.json \
    --indent 4
```

| 選項 | 預設值 | 說明 |
|------|--------|------|
| `--output` / `-o` | `analysis_report.json` | JSON 報表路徑 |
| `--indent` | `2` | JSON 縮排層數；`0` 輸出緊湊格式 |

### gemini/

```bash
make -C gemini run DIR=/path/to/your/php/project
# 或直接執行：
python3 gemini/php_analyzer.py /path/to/your/php/project
```

執行後會在**當前工作目錄**產生 `analysis_report.json`，並在終端機印出摘要。

---

## 執行測試

### 一次跑完整專案（推薦）

在 repo root：

```bash
make test
```

（選用）執行 lint（需先 `python3 -m pip install ruff`）：

```bash
make lint
```

### 各版本分開執行

```bash
make -C claude test    # unittest + py_compile
make -C codex  test    # unittest + py_compile
make -C gemini test    # unittest + py_compile
```

執行 lint（需先 `python3 -m pip install ruff`）：

```bash
make -C claude lint
```

---

## CI / CD（GitHub Actions）

- CI：`.github/workflows/ci.yml`（push / PR 時執行；跑多個 Python 版本 + unit tests + `claude/` lint）
- Release（CD）：`.github/workflows/release.yml`（推 tag `v*` 時觸發；會跑測試、打包 zip，並建立 GitHub Release 上傳附件）

示例（建立 release）：

```bash
git tag v1.0.0
git push origin v1.0.0
```

---

## 輸出報表格式

各版本的 JSON 結構相似，核心欄位如下：

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

> **注意**：`claude/` 與 `codex/` 在分析前會將字串內容替換為空字串佔位符，因此 `condition` 欄位中的字串鍵值（如 `$item['type']`）會顯示為 `$item['']`，此為預期行為。

---

## 注意事項

這是 *best-effort* 的文字掃描器，對於以下情境可能有誤判：

- 動態拼接的 PHP 程式碼
- 非常不規則的縮排或大括號格式
- 巨型 heredoc / 動態字串中夾雜控制流程關鍵字

如需 100% 精確的 AST 分析，請考慮使用 `nikic/php-parser` 等完整解析器。
