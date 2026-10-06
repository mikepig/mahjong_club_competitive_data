CREATE OR REPLACE FUNCTION record_game(
    p_play_date DATE,
    p_table_no  INTEGER,
    p_players   TEXT[],
    p_scores    INTEGER[]
)
RETURNS BIGINT                      -- the new match_id
LANGUAGE plpgsql
SECURITY DEFINER                    -- explained in Part C
SET search_path = public
AS $$
DECLARE
    v_match_id BIGINT;
    v_missing  TEXT;
BEGIN
    IF cardinality(p_players) <> 4 OR cardinality(p_scores) <> 4 THEN
        RAISE EXCEPTION 'Need exactly 4 players and 4 scores';
    END IF;

    -- TODO A: find any name in p_players that is NOT in the players table
    --         (hint: you used NOT EXISTS in the trigger)
    SELECT name INTO v_missing
    FROM unnest(p_players) AS name
    WHERE NOT EXISTS (SELECT 1 FROM players WHERE player_name = name);

    IF v_missing IS NOT NULL THEN
        RAISE EXCEPTION 'Unknown player: %', v_missing;
    END IF;

    -- TODO B: insert the game into matches and capture its id into v_match_id
    INSERT INTO matches (play_date, table_no)
    VALUES (p_play_date, p_table_no)
    RETURNING match_id INTO v_match_id;

    -- TODO C: insert the 4 results, turning names into player_ids
    INSERT INTO match_results (match_id, player_id, score)
    SELECT v_match_id, p.player_id, t.score
    FROM unnest(p_players, p_scores) AS t(player_name, score)
    JOIN players p ON p.player_name = t.player_name;

    RETURN v_match_id;
END;
$$;

-- Functions are executable by EVERYONE by default, and Supabase exposes them through its public API.
REVOKE EXECUTE ON FUNCTION record_game(DATE, INTEGER, TEXT[], INTEGER[]) FROM PUBLIC, anon, authenticated;

-- Login for the entry form: it can ONLY call record_game (no direct table access).
-- Replace CHANGE_ME with a real password in the SQL Editor only; keep CHANGE_ME in this file.
-- Run CREATE ROLE once; if club_writer already exists, skip that line.
CREATE ROLE club_writer WITH LOGIN PASSWORD 'CHANGE_ME';
GRANT USAGE ON SCHEMA public TO club_writer;
GRANT EXECUTE ON FUNCTION record_game(DATE, INTEGER, TEXT[], INTEGER[]) TO club_writer;


CREATE OR REPLACE FUNCTION add_player(p_name TEXT)
RETURNS BIGINT                      -- the new player_id
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_player_id BIGINT;
BEGIN
    INSERT INTO players (player_name)
    VALUES (trim(p_name))
    RETURNING player_id INTO v_player_id;

    RETURN v_player_id;
END;
$$;

REVOKE EXECUTE ON FUNCTION add_player(TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION add_player(TEXT) TO club_writer;
