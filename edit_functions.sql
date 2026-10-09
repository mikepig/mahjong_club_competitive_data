-- Edit or delete a recorded game. Run after insert_tables.sql (needs the club_writer role).
-- Both run as their owner (SECURITY DEFINER), so club_writer still has no direct table access.


-- Replace a game's date, table, players and scores.
-- Same inputs as record_game, plus which game to change.
CREATE OR REPLACE FUNCTION update_game(
    p_match_id  BIGINT,
    p_play_date DATE,
    p_table_no  INTEGER,
    p_players   TEXT[],
    p_scores    INTEGER[]
)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_missing TEXT;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM matches WHERE match_id = p_match_id) THEN
        RAISE EXCEPTION 'Game % does not exist', p_match_id;
    END IF;

    IF cardinality(p_players) <> 4 OR cardinality(p_scores) <> 4 THEN
        RAISE EXCEPTION 'Need exactly 4 players and 4 scores';
    END IF;

    SELECT name INTO v_missing
    FROM unnest(p_players) AS name
    WHERE NOT EXISTS (SELECT 1 FROM players WHERE player_name = name);

    IF v_missing IS NOT NULL THEN
        RAISE EXCEPTION 'Unknown player: %', v_missing;
    END IF;

    UPDATE matches
    SET play_date = p_play_date, table_no = p_table_no
    WHERE match_id = p_match_id;

    -- Simplest correct way to change who played: remove the old 4 results, insert the new 4.
    -- The deferred trigger only checks at COMMIT, so the moment with 0 results in between is fine.
    DELETE FROM match_results WHERE match_id = p_match_id;

    INSERT INTO match_results (match_id, player_id, score)
    SELECT p_match_id, p.player_id, t.score
    FROM unnest(p_players, p_scores) AS t(player_name, score)
    JOIN players p ON p.player_name = t.player_name;

    RETURN p_match_id;
END;
$$;


-- Delete a game entirely (its 4 results go with it via ON DELETE CASCADE).
CREATE OR REPLACE FUNCTION delete_game(p_match_id BIGINT)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_match_id BIGINT;
BEGIN
    DELETE FROM matches WHERE match_id = p_match_id
    RETURNING match_id INTO v_match_id;

    IF v_match_id IS NULL THEN
        RAISE EXCEPTION 'Game % does not exist', p_match_id;
    END IF;

    RETURN v_match_id;
END;
$$;


REVOKE EXECUTE ON FUNCTION update_game(BIGINT, DATE, INTEGER, TEXT[], INTEGER[]) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION delete_game(BIGINT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION update_game(BIGINT, DATE, INTEGER, TEXT[], INTEGER[]) TO club_writer;
GRANT EXECUTE ON FUNCTION delete_game(BIGINT) TO club_writer;
