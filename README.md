# 台灣樂透數據工具（Taiwan Lotto）

Taiwan Lotto 是一個 Python CLI 資料收集與分析工具，目標是收集、儲存、查詢與分析台灣大樂透及威力彩歷史開獎資料。本專案並非台灣彩券官方服務，開獎結果以官方公告為準。

## 專案概覽

| 項目 | 內容 |
| :--- | :--- |
| **核心目標** | 收集、儲存、查詢與分析大樂透及威力彩開獎資料 |
| **專案類型** | Python CLI 資料收集工具與本機唯讀 Web 分析介面 |
| **部署目標** | 以 Windows 本機為主；CLI 開發與執行支援 macOS / Linux，Web 介面固定供本機存取 |

## 快速開始

### 1. 環境準備

- Python 3.13.x
- Git

Windows PowerShell：

```powershell
git clone git@github.com:tuchiayu/taiwan-lotto-pub.git
Set-Location taiwan-lotto-pub
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt
pip install -e .
Copy-Item .env.example .env
```

macOS / Linux：

```bash
git clone git@github.com:tuchiayu/taiwan-lotto-pub.git
cd taiwan-lotto-pub
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt
pip install -e .
cp .env.example .env
```

### 2. 執行

```text
taiwan-lotto --help
taiwan-lotto --version
taiwan-lotto sync
taiwan-lotto web
taiwan-lotto web --no-sync
```

`taiwan-lotto sync` 第一次執行時會建立 `data/taiwan_lotto.db`，並從台彩官網目前使用的月份 API 匯入大樂透（2007 年起）與威力彩（2008 年起）的官方歷史資料。後續執行會分別從各彩券最新資料月份往前兩個月查到目前月份，新增最新期別、補回近期缺期並比對官方修正。

同步指令不包含背景排程；需要更新資料時手動執行即可。資料庫檔不進入 Git，備份前先確認沒有同步程序執行，再複製 `data/taiwan_lotto.db`。

`taiwan-lotto web` 預設由 CLI 先同步最新開獎資料，再於 `http://127.0.0.1:4938`（可用 `--port` 指定其他 port）啟動唯讀的本機 Web 介面，並於服務就緒後自動開啟瀏覽器（`--no-browser` 可關閉）；`Ctrl+C` 停止服務。啟動前的同步可能建立或更新 `data/taiwan_lotto.db`，Web 查詢層僅讀取資料。

同步失敗時，會檢查同步後的資料庫檔案是否存在：若已存在，仍會顯示警告並啟動 Web；若尚無開獎紀錄，頁面會顯示無資料提示。首次同步可能在下載失敗前就已建立空資料庫，因此不會僅因首次同步失敗而停止啟動。若同步失敗後資料庫檔案仍不存在，則不啟動 Web。

離線使用、開發或除錯時可加上 `--no-sync`，略過啟動前同步並直接啟動 Web。此時即使資料庫不存在，也會啟動並顯示缺少資料的提示，不會建立資料庫。

首頁可依彩券與日期區間瀏覽逐期開獎資料；`/stats` 可使用全部資料、日期區間或最近期數，查看獎號／第一區與特別號／第二區的開出次數、開出率、與理論差異、最近開出日期及未開期數，並可點擊表格欄位排序。僅限本機存取，不提供遠端或多使用者部署。

### 3. 測試

執行完整測試前，需在虛擬環境安裝 Playwright 使用的 Chromium。Windows / macOS：

```text
python -m playwright install chromium
```

Linux 同時安裝瀏覽器所需的系統套件（可能需要管理員權限）：

```bash
python -m playwright install --with-deps chromium
```

```text
ruff format --check .
ruff check .
pytest --cov=src --cov-report=term-missing --cov-fail-under=80
pip-audit -r requirements.txt
pip-audit -r requirements-dev.txt
pre-commit run --all-files
```

完整 `pytest` 包含 `tests/e2e` 的無頭 Chromium 互動測試，使用臨時 SQLite 與本機隨機 port，不讀取正式資料庫或執行台彩同步。只跑單元／整合測試可用 `pytest tests/unit tests/integration`；只跑瀏覽器測試可用 `pytest tests/e2e`。

瀏覽器測試失敗時，會在 `test-results/` 保留 trace 與截圖（已排除於 Git），可用 `python -m playwright show-trace "test-results/<測試目錄>/trace.zip"` 開啟 trace。CI 的失敗產物可從 `browser-test-failures` artifact 下載，保留 7 天。

## 目前範圍

目前 repository 提供大樂透與威力彩的 SQLite 資料庫、官方歷史匯入、手動增量同步、本機逐期開獎查詢，以及依彩券、日期區間或最近期數篩選的可排序統計資料。

尚未提供背景排程、CSV 匯出、統計圖表、號碼組合分析或號碼預估；這些功能將於後續視需求另行評估。

## License

[MIT License](./LICENSE) © 2026 Wilson Tu
