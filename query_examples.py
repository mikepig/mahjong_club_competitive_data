"""Example queries against the club database. Run: python query_examples.py"""

import pandas as pd

from db import get_engine

engine = get_engine()

print("Leaderboard")
print(pd.read_sql("SELECT * FROM leaderboard ORDER BY rank", engine).to_string(index=False))

print("\nEvery game, newest first")
games = pd.read_sql("SELECT * FROM match_scores ORDER BY play_date DESC, match_id DESC, placement", engine)
print(games.to_string(index=False))

print("\nHow often each player finishes in each place")
print(pd.crosstab(games["player_name"], games["placement"]))

# Parameterised query: never paste user input straight into SQL text.
name = "Mike"
mike = pd.read_sql(
    "SELECT play_date, placement, score, pts FROM match_scores WHERE player_name = %(name)s ORDER BY play_date",
    engine,
    params={"name": name},
)
print(f"\n{name}'s games")
print(mike.to_string(index=False))
