-- Read-only login used by the dashboard and by club members running their own queries.
-- Run once in the Supabase SQL Editor (the role survives table rebuilds).
--
-- Replace CHANGE_ME with a strong password in the SQL Editor ONLY.
-- Never commit the real password: keep CHANGE_ME in this file.
CREATE ROLE club_reader WITH LOGIN PASSWORD 'CHANGE_ME';

GRANT USAGE ON SCHEMA public TO club_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO club_reader;                  -- existing tables and views
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO club_reader;  -- ones created later


-- RLS policies only apply to the roles they name, so club_reader needs its own read policies.
-- Re-run this part after every create_tables.sql rebuild (dropping a table drops its policies).
DROP POLICY IF EXISTS "club_reader can read players" ON players;
CREATE POLICY "club_reader can read players" ON players FOR SELECT TO club_reader USING (true);

DROP POLICY IF EXISTS "club_reader can read matches" ON matches;
CREATE POLICY "club_reader can read matches" ON matches FOR SELECT TO club_reader USING (true);

DROP POLICY IF EXISTS "club_reader can read results" ON match_results;
CREATE POLICY "club_reader can read results" ON match_results FOR SELECT TO club_reader USING (true);
