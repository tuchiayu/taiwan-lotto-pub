BEGIN IMMEDIATE;
DROP TABLE IF EXISTS sync_state;
DROP INDEX IF EXISTS idx_draw_numbers_game_number;
DROP TABLE IF EXISTS draw_numbers;
DROP INDEX IF EXISTS idx_draws_game_date;
DROP TABLE IF EXISTS draws;
DROP TABLE IF EXISTS games;
PRAGMA user_version = 0;
COMMIT;
