-- Sample data: the two games from "Mahjong scoring calculator.xlsx" (2026-10-01).
-- Run after create_tables.sql (which empties the tables).

INSERT INTO players (player_name) VALUES
    ('Mike'), ('Alvin'), ('Josh'), ('Grant'),
    ('Henry'), ('Yuhan'), ('Soi'), ('Kazuma');

INSERT INTO matches (play_date, table_no) VALUES
    ('2026-10-01', 1),
    ('2026-10-01', 2);

-- match_id and player_id are auto-numbered, so look them up by date/table and name
-- instead of guessing the numbers.
INSERT INTO match_results (match_id, player_id, score)
SELECT m.match_id, p.player_id, v.score
FROM (VALUES
    (1, 'Mike',   39600),
    (1, 'Alvin',  31200),
    (1, 'Josh',   24000),
    (1, 'Grant',   5200),
    (2, 'Henry',  52700),
    (2, 'Yuhan',  26400),
    (2, 'Soi',    11300),
    (2, 'Kazuma',  9600)
) AS v (table_no, player_name, score)
JOIN matches m ON m.play_date = '2026-10-01' AND m.table_no = v.table_no
JOIN players p ON p.player_name = v.player_name;
