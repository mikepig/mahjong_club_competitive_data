ALTER TABLE matches ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anyone can read matches"
ON matches
FOR SELECT 
TO anon, authenticated 
USING (true); 

ALTER TABLE players ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anyone can read players"
ON players
FOR SELECT
TO anon, authenticated 
USING (true); 

ALTER TABLE match_results ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anyone can read results"
ON match_results
FOR SELECT
TO anon, authenticated 
USING (true); 