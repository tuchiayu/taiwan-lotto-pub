# Changelog

本專案的重要變更會記錄在此文件。格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，版本號採用 [Semantic Versioning](https://semver.org/lang/zh-TW/)。

## [0.1.0] - 2026-08-31

### 新增

- 大樂透與威力彩開獎資料的 SQLite 儲存與官方歷史匯入（大樂透 2007 年起、威力彩 2008 年起）
- `taiwan-lotto sync`：手動增量同步指令，補回近期缺期並比對官方修正
- `taiwan-lotto web`：本機唯讀 Web 介面首頁，可依彩券與日期區間瀏覽逐期開獎資料
- 統計頁面（`/stats`）：查看各號碼的開出次數與開出率
- 初版公開發布
