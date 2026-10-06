DROP TABLE IF EXISTS "Match_Results";
DROP TABLE IF EXISTS "Matches";
DROP TABLE IF EXISTS "Players";
DROP TABLE IF EXISTS match_results;
DROP TABLE IF EXISTS matches;
DROP TABLE IF EXISTS players;


CREATE TABLE players (
    player_id   BIGINT GENERATED ALWAYS AS IDENTITY,
    player_name TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (player_id),
    CHECK (trim(player_name) <> '')
);


CREATE TABLE matches (
    match_id   BIGINT GENERATED ALWAYS AS IDENTITY,
    play_date  DATE NOT NULL,
    table_no   INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (match_id),
    CHECK (table_no > 0)
);

CREATE TABLE match_results (
    match_id  BIGINT NOT NULL,               
    player_id BIGINT NOT NULL,         
    score     INTEGER NOT NULL, 

    PRIMARY KEY (match_id, player_id),       
    FOREIGN KEY (match_id)  REFERENCES matches (match_id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players (player_id),
    CHECK (score % 100 = 0)           
);
