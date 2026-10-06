DROP VIEW IF EXISTS leaderboard;
DROP VIEW IF EXISTS match_scores;
CREATE VIEW match_scores AS
WITH ranked AS(
  SELECT p.player_id, p.player_name, r.score, m.play_date, m.table_no, m.match_id, (r.score::double precision-30000)/1000 AS raw_pts, rank() OVER (PARTITION BY r.match_id ORDER BY r.score DESC) AS placement
  FROM match_results r
  LEFT JOIN players p ON r.player_id=p.player_id
  JOIN matches m ON m.match_id=r.match_id
)
SELECT *, raw_pts+ CASE placement WHEN 1 THEN 15 WHEN 2 THEN 5 WHEN 3 THEN -5 WHEN 4 THEN -15 END AS pts FROM ranked;

CREATE VIEW leaderboard AS
WITH player_stats AS(
  SELECT player_id, player_name, SUM(pts) as total_pts, COUNT(*) as match_played, ROUND(AVG(score),0) as average_points_earned FROM match_scores
  GROUP BY player_id, player_name
)
SELECT player_name,total_pts, match_played, average_points_earned, total_pts +1000 as rating, rank() OVER (ORDER BY total_pts DESC)
FROM player_stats
ORDER BY total_pts;
