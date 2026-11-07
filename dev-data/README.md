# 開發資料 (Development Data)

從本 repo 的原始碼執行 `taiwan-lotto`（例如 `pip install -e .` 後）時，若沒有指定 `--data-dir` 或環境變數 `TLL_DATA_DIR`，資料庫 `taiwan_lotto.db` 放在這個資料夾，不會讀寫安裝版（`pip install .`、`pipx`、`uv tool`）使用的資料（Windows `%LOCALAPPDATA%\TaiwanLotto\data`、其他系統 `~/.local/share/taiwan-lotto`）。

- 這個檔案是開發版的標記，請保留；資料夾內其他檔案都不進版控。
- `taiwan-lotto sync`／`web` 執行時印出的 `Database:` 會標示 `(development data)`。
- 第一次執行 `sync` 時會建立資料庫，並從台彩官網匯入完整歷史（約 9 秒）。

需要使用其他位置的資料時，以 `--data-dir <路徑>` 或 `TLL_DATA_DIR` 明確指定。
