# Changelog

本專案的重要變更會記錄在此文件。格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，版本號採用 [Semantic Versioning](https://semver.org/lang/zh-TW/)。

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
