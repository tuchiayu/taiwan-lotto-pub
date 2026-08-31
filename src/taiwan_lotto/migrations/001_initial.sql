BEGIN IMMEDIATE;

CREATE TABLE games (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    main_number_max INTEGER NOT NULL CHECK (main_number_max > 0),
    special_number_max INTEGER NOT NULL CHECK (special_number_max > 0)
);

CREATE TABLE draws (
    game_code TEXT NOT NULL,
    draw_term TEXT NOT NULL CHECK (
        length(draw_term) IN (8, 9)
        AND draw_term NOT GLOB '*[^0-9]*'
    ),
    draw_date TEXT NOT NULL,
    special_number INTEGER NOT NULL CHECK (special_number > 0),
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (game_code, draw_term),
    FOREIGN KEY (game_code) REFERENCES games(code)
);

CREATE INDEX idx_draws_game_date ON draws(game_code, draw_date);

CREATE TABLE draw_numbers (
    game_code TEXT NOT NULL,
    draw_term TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position BETWEEN 1 AND 6),
    number INTEGER NOT NULL CHECK (number > 0),
    PRIMARY KEY (game_code, draw_term, position),
    UNIQUE (game_code, draw_term, number),
    FOREIGN KEY (game_code, draw_term)
        REFERENCES draws(game_code, draw_term)
        ON DELETE CASCADE
);

CREATE INDEX idx_draw_numbers_game_number
    ON draw_numbers(game_code, number);

CREATE TABLE sync_state (
    game_code TEXT PRIMARY KEY,
    history_complete INTEGER NOT NULL DEFAULT 0
        CHECK (history_complete IN (0, 1)),
    history_completed_at TEXT,
    last_success_at TEXT,
    FOREIGN KEY (game_code) REFERENCES games(code)
);

INSERT INTO games (code, name, main_number_max, special_number_max) VALUES
    ('lotto649', '大樂透', 49, 49),
    ('super_lotto638', '威力彩', 38, 8);

CREATE TRIGGER validate_draw_special_number_insert
BEFORE INSERT ON draws
WHEN NEW.special_number > (
    SELECT special_number_max FROM games WHERE code = NEW.game_code
)
BEGIN
    SELECT RAISE(ABORT, 'special number outside game range');
END;

CREATE TRIGGER validate_draw_special_number_update
BEFORE UPDATE OF special_number, game_code ON draws
WHEN NEW.special_number > (
    SELECT special_number_max FROM games WHERE code = NEW.game_code
)
BEGIN
    SELECT RAISE(ABORT, 'special number outside game range');
END;

CREATE TRIGGER validate_draw_main_number_insert
BEFORE INSERT ON draw_numbers
WHEN NEW.number > (
    SELECT main_number_max FROM games WHERE code = NEW.game_code
)
BEGIN
    SELECT RAISE(ABORT, 'main number outside game range');
END;

CREATE TRIGGER validate_draw_main_number_update
BEFORE UPDATE OF number, game_code ON draw_numbers
WHEN NEW.number > (
    SELECT main_number_max FROM games WHERE code = NEW.game_code
)
BEGIN
    SELECT RAISE(ABORT, 'main number outside game range');
END;

PRAGMA user_version = 1;
COMMIT;
