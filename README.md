# mahjong_club_competitive_data

Cloud database and live dashboard for the mahjong club's scores.

The database (Supabase / Postgres) stores **facts only**: players, games, and each player's final score.
Placement, pts, ratings and the leaderboard are calculated by SQL views, so they update the moment a score changes.

## Scoring

| | |
|---|---|
| Raw pts | (final score − 30,000) ÷ 1,000 |
| Placement bonus | 1st +15, 2nd +5, 3rd −5, 4th −15 |
| Pts | raw + placement bonus |
| Rating | 1000 + total pts |

Every game must have exactly 4 players whose final scores add up to 100,000 (enforced by a trigger).

## Database files

Run in the Supabase SQL Editor, in this order:

| File | What it does |
|---|---|
| `create_tables.sql` | `players`, `matches`, `match_results` (drops and recreates them, **deleting all data**) |
| `check_functions.sql` | Trigger: 4 players and a 100,000 total per game, checked at commit |
| `security.sql` | Row Level Security: public can read, nobody can write through the API |
| `readonly_role.sql` | `club_reader` read-only login (role part once; policy part after every rebuild) |
| `seed_data.sql` | The first two games from the original spreadsheet |
| `create_views.sql` | `match_scores` (placement, pts per game) and `leaderboard` |

Enter a game in one transaction so the trigger sees all 4 rows together:

```sql
BEGIN;
WITH m AS (
    INSERT INTO matches (play_date, table_no) VALUES ('2026-10-08', 1)
    RETURNING match_id
)
INSERT INTO match_results (match_id, player_id, score)
SELECT m.match_id, p.player_id, v.score
FROM m, (VALUES ('Mike', 40000), ('Alvin', 30000), ('Josh', 20000), ('Grant', 10000)) AS v (name, score)
JOIN players p ON p.player_name = v.name;
COMMIT;
```

## Python setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env                                     # for scripts / notebooks
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # for the dashboard
```

Fill the real `club_reader` connection string into `.env` and `.streamlit/secrets.toml` (both are gitignored).
Never put a real password in the `.example` files: those are committed.

## Querying from Python

```python
import pandas as pd
from db import get_engine

df = pd.read_sql("SELECT * FROM leaderboard ORDER BY rank", get_engine())
```

`query_examples.py` has more examples.

## Dashboard

```bash
.venv/bin/streamlit run app.py
```

Tabs: leaderboard, player profile (rating over time, placement counts), game log.
Data is cached for 60 seconds; the **Refresh data** button reloads immediately.

### Deploying for the club (Streamlit Community Cloud)

1. Push this repo to GitHub.
2. At share.streamlit.io, create an app from this repo with `app.py` as the main file.
3. In the app's **Settings → Secrets**, paste the contents of your local `.streamlit/secrets.toml`.
4. Share the app URL. It reads through the read-only `club_reader` login, so visitors cannot change data.
