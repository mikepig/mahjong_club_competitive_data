CREATE OR REPLACE FUNCTION check_match_complete()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER        -- deferred: runs at COMMIT as the caller (e.g. club_writer, who can't read tables)
SET search_path = public
AS $$
DECLARE
    v_match_id BIGINT;
    v_players  INTEGER;
    v_total    INTEGER;
BEGIN
    -- Which game was touched? (DELETE only has OLD; INSERT/UPDATE have NEW)
    IF TG_OP = 'DELETE' THEN
        v_match_id := OLD.match_id;
    ELSE
        v_match_id := NEW.match_id;
    END IF;

    -- If the whole game was deleted, there's nothing to check
    IF NOT EXISTS (SELECT 1 FROM matches WHERE match_id = v_match_id) THEN
        RETURN NULL;
    END IF;

    -- TODO 1: count the players and sum the scores for this game
    SELECT COUNT(player_id), SUM(score)
    INTO v_players, v_total
    FROM match_results
    WHERE match_id = v_match_id;

    IF v_players <> 4 THEN
        RAISE EXCEPTION 'Match % has % players, expected 4', v_match_id, v_players;
    END IF;

    -- TODO 2: write the same kind of IF for the 100,000 total
    IF v_total<>100000 THEN 
        RAISE EXCEPTION 'Total Score is %, expected 100,000', v_total;
    END IF;

    RETURN NULL;   -- AFTER triggers ignore the return value
END;
$$;

CREATE CONSTRAINT TRIGGER match_must_be_complete
AFTER INSERT OR UPDATE OR DELETE ON match_results
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION check_match_complete();