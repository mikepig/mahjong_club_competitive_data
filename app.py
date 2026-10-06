"""Mahjong club dashboard.

Reads the `leaderboard` and `match_scores` views from Supabase. All scoring logic
lives in the database; this app only displays it.

Games are entered through the database functions `record_game` and `add_player`,
using the separate `club_writer` login (it can call those two functions and nothing else).
"""

import hmac
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy import text

REFRESH_SECONDS = 60          # how long query results are cached before re-reading the database
STARTING_RATING = 1000
GAME_TOTAL = 100_000
DEFAULT_SCORE = 25_000
SERIES_COLOR = "#2e7d32"      # dark green: readable on the mint background

st.set_page_config(page_title="Mahjong Club", page_icon="🀄", layout="wide")

conn = st.connection("sql")   # read-only club_reader login, from .streamlit/secrets.toml


# ---------------------------------------------------------------- data

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


def load_player_names() -> list[str]:
    """Every member, including ones who haven't played yet (the leaderboard only has players with games)."""
    names = conn.query("SELECT player_name FROM players ORDER BY player_name", ttl=REFRESH_SECONDS)
    return names["player_name"].tolist()


def placement_stats(scores: pd.DataFrame) -> pd.DataFrame:
    """Average placement and 1st/4th-place rates per player."""
    return scores.groupby("player_name").agg(
        avg_placement=("placement", "mean"),
        first_rate=("placement", lambda p: (p == 1).mean()),
        fourth_rate=("placement", lambda p: (p == 4).mean()),
    ).reset_index()


def entry_configured() -> bool:
    return "admin_password" in st.secrets and "writer" in st.secrets.get("connections", {})


def call_db_function(sql: str, params: dict):
    """Run `SELECT some_function(...)` as club_writer and commit. Returns the function's result.

    The match trigger is deferred, so a bad game is rejected at commit and raises here.
    """
    writer = st.connection("writer", type="sql")
    with writer.session as session:
        result = session.execute(text(sql), params).scalar_one()
        session.commit()
    return result


def db_error_message(exc: Exception) -> str:
    """The database's own message (e.g. 'Unknown player: Alvn'), without driver noise."""
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    return getattr(diag, "message_primary", None) or str(exc)


def refresh_data() -> None:
    st.cache_data.clear()


# ---------------------------------------------------------------- tabs

def render_leaderboard(leaderboard: pd.DataFrame, scores: pd.DataFrame) -> None:
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


def render_player_profile(leaderboard: pd.DataFrame, scores: pd.DataFrame) -> None:
    player = st.selectbox("Player", leaderboard["player_name"].tolist())
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


def render_game_log(scores: pd.DataFrame) -> None:
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


def render_admin_login() -> None:
    st.write("Game entry is for club admins.")
    password = st.text_input("Admin password", type="password")
    if st.button("Unlock"):
        if hmac.compare_digest(password.encode(), str(st.secrets["admin_password"]).encode()):
            st.session_state.admin_ok = True
            st.rerun()
        else:
            st.error("Wrong password.")


def render_game_entry() -> None:
    if flash := st.session_state.pop("flash", None):
        st.success(flash)

    names = load_player_names()
    form_id = st.session_state.setdefault("form_id", 0)   # bumping this resets every input below

    date_col, table_col = st.columns(2)
    play_date = date_col.date_input("Date", value=date.today(), key=f"date_{form_id}")
    table_no = table_col.number_input("Table", min_value=1, step=1, value=1, key=f"table_{form_id}")

    players, scores = [], []
    for i in range(4):
        name_col, score_col = st.columns([2, 1])
        players.append(name_col.selectbox(
            f"Player {i + 1}", names, index=None, placeholder="Choose a player", key=f"player{i}_{form_id}",
        ))
        scores.append(int(score_col.number_input(
            "Final score", value=DEFAULT_SCORE, step=100, format="%d", key=f"score{i}_{form_id}",
        )))

    # Same rules the database enforces, checked here first so mistakes show before submitting.
    problems = []
    if None in players:
        problems.append("Choose all 4 players.")
    elif len(set(players)) < 4:
        problems.append("A player is listed more than once.")
    total = sum(scores)
    if total != GAME_TOTAL:
        problems.append(f"Scores add up to {total:,}, which is {total - GAME_TOTAL:+,} off {GAME_TOTAL:,}.")
    if any(s % 100 for s in scores):
        problems.append("Scores must be multiples of 100.")

    st.markdown(f"**Total: {total:,}** {'✅' if total == GAME_TOTAL else '❌'}")
    for problem in problems:
        st.warning(problem)

    if None not in players and len(set(players)) == 4:
        preview = pd.DataFrame({"Player": players, "Final score": scores})
        preview["Place"] = preview["Final score"].rank(method="min", ascending=False).astype(int)
        st.caption("Placement preview (pts are calculated by the database after saving)")
        st.dataframe(preview.sort_values("Place")[["Place", "Player", "Final score"]], hide_index=True)

    if st.button("Save game", type="primary", disabled=bool(problems)):
        try:
            match_id = call_db_function(
                "SELECT record_game(CAST(:play_date AS date), :table_no, CAST(:players AS text[]), CAST(:scores AS integer[]))",
                {"play_date": play_date, "table_no": int(table_no), "players": players, "scores": scores},
            )
        except Exception as exc:
            st.error(f"Not saved: {db_error_message(exc)}")
        else:
            st.session_state.flash = f"Saved game #{match_id} ({play_date:%b %d}, table {int(table_no)})."
            st.session_state.form_id += 1
            refresh_data()
            st.rerun()

    with st.expander("Add a new player"):
        new_name = st.text_input("Name", key=f"new_player_{form_id}")
        if st.button("Add player", disabled=not new_name.strip()):
            try:
                call_db_function("SELECT add_player(:name)", {"name": new_name})
            except Exception as exc:
                st.error(f"Not added: {db_error_message(exc)}")
            else:
                st.session_state.flash = f"Added {new_name.strip()}. They're now in the player lists."
                st.session_state.form_id += 1
                refresh_data()
                st.rerun()

    if st.button("Lock entry"):
        st.session_state.admin_ok = False
        st.rerun()


# ---------------------------------------------------------------- page

title_col, refresh_col = st.columns([5, 1])
title_col.title("🀄 Mahjong Club")
if refresh_col.button("Refresh data", use_container_width=True):
    refresh_data()
    st.rerun()

leaderboard = load_leaderboard()
scores = load_scores()
has_games = not scores.empty

if has_games:
    m1, m2, m3 = st.columns(3)
    m1.metric("Players", scores["player_name"].nunique())
    m2.metric("Games played", scores["match_id"].nunique())
    m3.metric("Last game", scores["play_date"].max().strftime("%b %d, %Y"))

tab_board, tab_player, tab_games, tab_entry = st.tabs(["Leaderboard", "Player profile", "Game log", "Enter a game"])

for tab, render in [
    (tab_board, lambda: render_leaderboard(leaderboard, scores)),
    (tab_player, lambda: render_player_profile(leaderboard, scores)),
    (tab_games, lambda: render_game_log(scores)),
]:
    with tab:
        if has_games:
            render()
        else:
            st.info("No games recorded yet.")

with tab_entry:
    if not entry_configured():
        st.info("Game entry isn't set up yet: the app's secrets need `admin_password` and a `[connections.writer]` section.")
    elif st.session_state.get("admin_ok"):
        render_game_entry()
    else:
        render_admin_login()
