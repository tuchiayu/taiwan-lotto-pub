# Changelog

本專案的重要變更會記錄在此文件。格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，版本號採用 [Semantic Versioning](https://semver.org/lang/zh-TW/)。

## [0.2.0] - 2026-11-07

### 新增

- 資料庫改存放在固定的資料夾，不再跟著執行指令時所在的資料夾：Windows 為 `%LOCALAPPDATA%\TaiwanLotto\data`，macOS／Linux 為 `~/.local/share/taiwan-lotto`；從原始碼執行時使用 repo 內的 `dev-data/`
- `sync`、`web` 新增 `--data-dir` 選項與 `TLL_DATA_DIR` 環境變數，可自行指定資料夾；執行時會先印出使用的資料庫路徑
- 舊版的 `data/taiwan_lotto.db` 不會自動搬移，新位置第一次同步約需 9 秒；確認無誤後可刪除舊檔

### 修正

- 網頁標題改為 `TAIWAN LOTTO`

### 其他

- 測試改為平行執行

## [0.1.1] - 2026-11-05

### 修正

- 以 `pip install .`、`pipx install` 或 `uv tool install` 直接安裝時，一併安裝執行所需套件（FastAPI、Jinja2、Uvicorn），不再出現 `No module named 'fastapi'`
- 統計頁變更排序後按瀏覽器上一頁／下一頁，兩張表格的排序會依網址正確還原

### 其他

- README 補充 `taiwan-lotto web` 啟動前同步與同步失敗時的行為
- 新增 Chromium 瀏覽器互動測試，CI 覆蓋率門檻提高至 80%

## [0.1.0] - 2026-08-31

### 新增

- 大樂透與威力彩開獎資料的 SQLite 儲存與官方歷史匯入（大樂透 2007 年起、威力彩 2008 年起）
- `taiwan-lotto sync`：手動增量同步指令，補回近期缺期並比對官方修正
- `taiwan-lotto web`：本機唯讀 Web 介面首頁，可依彩券與日期區間瀏覽逐期開獎資料
- 統計頁面（`/stats`）：查看各號碼的開出次數與開出率
- 初版公開發布
