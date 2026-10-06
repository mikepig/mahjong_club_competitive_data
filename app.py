"""Mahjong club dashboard.

Reads the `leaderboard` and `match_scores` views from Supabase. All scoring logic
lives in the database; this app only displays it.
"""

import altair as alt
import pandas as pd
import streamlit as st

REFRESH_SECONDS = 60          # how long query results are cached before re-reading the database
STARTING_RATING = 1000
SERIES_COLOR = "#2e7d32"           # dark green: readable on the mint background

st.set_page_config(page_title="Mahjong Club", page_icon="🀄", layout="wide")

conn = st.connection("sql")   # connection details come from .streamlit/secrets.toml


def load_leaderboard() -> pd.DataFrame:
    return conn.query(
        """
        SELECT rank, player_name, rating, total_pts, match_played, average_points_earned
        FROM leaderboard
        ORDER BY rank, player_name
        """,
        ttl=REFRESH_SECONDS,
    )


def load_scores() -> pd.DataFrame:
    df = conn.query(
        """
        SELECT match_id, play_date, table_no, player_name, score, placement, raw_pts, pts
        FROM match_scores
        """,
        ttl=REFRESH_SECONDS,
    )
    df["play_date"] = pd.to_datetime(df["play_date"]).dt.date
    return df.sort_values(["play_date", "match_id", "placement"]).reset_index(drop=True)


def placement_stats(scores: pd.DataFrame) -> pd.DataFrame:
    """Average placement and 1st/4th-place rates per player."""
    return scores.groupby("player_name").agg(
        avg_placement=("placement", "mean"),
        first_rate=("placement", lambda p: (p == 1).mean()),
        fourth_rate=("placement", lambda p: (p == 4).mean()),
    ).reset_index()


# ---------------------------------------------------------------- header

title_col, refresh_col = st.columns([5, 1])
title_col.title("🀄 Mahjong Club")
if refresh_col.button("Refresh data", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

leaderboard = load_leaderboard()
scores = load_scores()

if scores.empty:
    st.info("No games recorded yet.")
    st.stop()

m1, m2, m3 = st.columns(3)
m1.metric("Players", scores["player_name"].nunique())
m2.metric("Games played", scores["match_id"].nunique())
m3.metric("Last game", scores["play_date"].max().strftime("%b %d, %Y"))

tab_board, tab_player, tab_games = st.tabs(["Leaderboard", "Player profile", "Game log"])

# ---------------------------------------------------------------- leaderboard

with tab_board:
    board = leaderboard.merge(placement_stats(scores), on="player_name", how="left")
    st.dataframe(
        board[[
            "rank", "player_name", "rating", "total_pts", "match_played",
            "avg_placement", "first_rate", "fourth_rate", "average_points_earned",
        ]],
        hide_index=True,
        use_container_width=True,
        column_config={
            "rank": st.column_config.NumberColumn("Rank", format="%d"),
            "player_name": "Player",
            "rating": st.column_config.NumberColumn("Rating", format="%.1f"),
            "total_pts": st.column_config.NumberColumn("Total pts", format="%+.1f"),
            "match_played": st.column_config.NumberColumn("Games", format="%d"),
            "avg_placement": st.column_config.NumberColumn("Avg place", format="%.2f"),
            "first_rate": st.column_config.ProgressColumn("1st rate", format="percent", min_value=0, max_value=1),
            "fourth_rate": st.column_config.ProgressColumn("4th rate", format="percent", min_value=0, max_value=1),
            "average_points_earned": st.column_config.NumberColumn("Avg final score", format="%d"),
        },
    )
    st.caption(f"Rating = {STARTING_RATING} + total pts. Updates automatically when scores change.")

# ---------------------------------------------------------------- player profile

with tab_player:
    players = leaderboard["player_name"].tolist()
    player = st.selectbox("Player", players)
    games = scores[scores["player_name"] == player].copy()
    games["game_no"] = range(1, len(games) + 1)
    games["rating"] = STARTING_RATING + games["pts"].cumsum()

    row = leaderboard[leaderboard["player_name"] == player].iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rank", f"#{int(row['rank'])}")
    c2.metric("Rating", f"{row['rating']:.1f}")
    c3.metric("Games", int(row["match_played"]))
    c4.metric("Avg placement", f"{games['placement'].mean():.2f}")

    chart_col, place_col = st.columns([2, 1])

    with chart_col:
        st.subheader("Rating over time")
        start = pd.DataFrame({"game_no": [0], "rating": [float(STARTING_RATING)]})
        rating_chart = (
            alt.Chart(pd.concat([start, games], ignore_index=True))
            .mark_line(color=SERIES_COLOR, strokeWidth=2, point=alt.OverlayMarkDef(size=64, color=SERIES_COLOR))
            .encode(
                x=alt.X("game_no:Q", title="Game", axis=alt.Axis(tickMinStep=1)),
                y=alt.Y("rating:Q", title="Rating", scale=alt.Scale(zero=False)),
                tooltip=[
                    alt.Tooltip("play_date:T", title="Date"),
                    alt.Tooltip("table_no:Q", title="Table"),
                    alt.Tooltip("placement:Q", title="Place"),
                    alt.Tooltip("score:Q", title="Final score", format=","),
                    alt.Tooltip("pts:Q", title="Pts", format="+.1f"),
                    alt.Tooltip("rating:Q", title="Rating", format=".1f"),
                ],
            )
        )
        baseline = alt.Chart(pd.DataFrame({"y": [STARTING_RATING]})).mark_rule(
            strokeDash=[4, 4], opacity=0.4
        ).encode(y="y:Q")
        st.altair_chart(baseline + rating_chart, use_container_width=True)

    with place_col:
        st.subheader("Placements")
        counts = (
            games["placement"].value_counts()
            .reindex([1, 2, 3, 4], fill_value=0)
            .rename_axis("placement").reset_index(name="games")
        )
        counts["label"] = counts["placement"].map({1: "1st", 2: "2nd", 3: "3rd", 4: "4th"})
        place_chart = (
            alt.Chart(counts)
            .mark_bar(color=SERIES_COLOR, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
            .encode(
                x=alt.X("label:N", title=None, sort=["1st", "2nd", "3rd", "4th"], axis=alt.Axis(labelAngle=0)),
                y=alt.Y("games:Q", title="Games", axis=alt.Axis(tickMinStep=1)),
                tooltip=[alt.Tooltip("label:N", title="Place"), alt.Tooltip("games:Q", title="Games")],
            )
        )
        st.altair_chart(place_chart, use_container_width=True)

    st.subheader("Games")
    st.dataframe(
        games.sort_values("game_no", ascending=False)[["play_date", "table_no", "placement", "score", "pts", "rating"]],
        hide_index=True,
        use_container_width=True,
        column_config={
            "play_date": "Date",
            "table_no": "Table",
            "placement": "Place",
            "score": st.column_config.NumberColumn("Final score", format="%d"),
            "pts": st.column_config.NumberColumn("Pts", format="%+.1f"),
            "rating": st.column_config.NumberColumn("Rating after", format="%.1f"),
        },
    )

# ---------------------------------------------------------------- game log

with tab_games:
    dates = sorted(scores["play_date"].unique(), reverse=True)
    picked = st.multiselect("Dates", dates, default=dates[:1], format_func=lambda d: d.strftime("%b %d, %Y"))
    shown = scores[scores["play_date"].isin(picked)] if picked else scores
    shown = shown.sort_values(["play_date", "match_id", "placement"], ascending=[False, False, True])

    for (match_id, play_date, table_no), game in shown.groupby(["match_id", "play_date", "table_no"], dropna=False, sort=False):
        table_label = f"Table {int(table_no)}" if pd.notna(table_no) else "No table"
        st.markdown(f"**{play_date:%b %d, %Y} · {table_label}** · game #{match_id}")
        st.dataframe(
            game[["placement", "player_name", "score", "raw_pts", "pts"]],
            hide_index=True,
            use_container_width=True,
            column_config={
                "placement": "Place",
                "player_name": "Player",
                "score": st.column_config.NumberColumn("Final score", format="%d"),
                "raw_pts": st.column_config.NumberColumn("Raw", format="%+.1f"),
                "pts": st.column_config.NumberColumn("Pts", format="%+.1f"),
            },
        )
