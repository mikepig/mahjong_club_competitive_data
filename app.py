"""Mahjong club dashboard.

Reads the `leaderboard` and `match_scores` views from Supabase. All scoring logic
lives in the database; this app only displays it.

Games are entered through the database functions `record_game` and `add_player`,
using the separate `club_writer` login (it can call those two functions and nothing else).
"""

import hmac
from datetime import date
from functools import partial

import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy import text

REFRESH_SECONDS = 60          # how long query results are cached before re-reading the database
STARTING_RATING = 1000
GAME_TOTAL = 100_000
SERIES_COLOR = "#2e7d32"      # dark green: readable on the mint background
RSVP_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSeCv4KW3y6vIam2rvqq5lIffssjNf-K9bqbNiqJV-ANOCn4Zg/viewform"

st.set_page_config(page_title="UM Mahjong League", page_icon="🀄", layout="wide")

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

TABS = ["Leaderboard", "Player profile", "Game log", "Enter a game"]


def open_profile(table_key: str, names: list[str]) -> None:
    """Click on any cell of a player's row -> switch to the Player profile tab for that player."""
    cells = st.session_state[table_key].selection.cells
    if not cells:
        return
    row, _column = cells[0]
    st.session_state.profile_player = names[row]
    st.session_state.tab = "Player profile"
    st.session_state[table_key] = {"selection": {"rows": [], "columns": [], "cells": []}}  # so the same click works again


def render_leaderboard(leaderboard: pd.DataFrame, scores: pd.DataFrame) -> None:
    board = leaderboard.merge(placement_stats(scores), on="player_name", how="left")
    st.dataframe(
        board[[
            "rank", "player_name", "rating", "total_pts", "match_played",
            "avg_placement", "first_rate", "fourth_rate", "average_points_earned",
        ]],
        hide_index=True,
        use_container_width=True,
        key="board",
        on_select=partial(open_profile, "board", board["player_name"].tolist()),
        selection_mode="single-cell",
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
    st.caption(
        f"Click a player to open their profile. Rating = {STARTING_RATING} + total pts. "
        "Updates automatically when scores change."
    )


def render_player_profile(leaderboard: pd.DataFrame, scores: pd.DataFrame) -> None:
    player = st.selectbox("Player", leaderboard["player_name"].tolist(), key="profile_player")
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
        table_key = f"game_{match_id}"
        st.dataframe(
            game[["placement", "player_name", "score", "raw_pts", "pts"]],
            hide_index=True,
            use_container_width=True,
            key=table_key,
            on_select=partial(open_profile, table_key, game["player_name"].tolist()),
            selection_mode="single-cell",
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
    with st.form("admin_login"):
        password = st.text_input("Admin password", type="password")
        unlocked = st.form_submit_button("Unlock")      # Enter in the field also submits
    if unlocked:
        if hmac.compare_digest(password.encode(), str(st.secrets["admin_password"]).encode()):
            st.session_state.admin_ok = True
            st.rerun()
        else:
            st.error("Wrong password.")


def parse_score(text: str) -> int | None:
    """'39,600' or ' 39600 ' -> 39600; anything that isn't a whole number -> None."""
    try:
        return int(text.replace(",", "").replace(" ", ""))
    except ValueError:
        return None


def resolve_player(text: str, names: list[str]) -> tuple[str | None, str | None]:
    """Match typed text to a member: case-insensitive, and a unique start of a name is enough.

    'joe' -> 'Joe', 'sog' -> 'Sogabe Sensei'. Returns (name, None) or (None, error message).
    """
    typed = text.strip().lower()
    if not typed:
        return None, "missing"
    for candidates in (
        [n for n in names if n.lower() == typed],
        [n for n in names if n.lower().startswith(typed)],
        [n for n in names if typed in n.lower()],
    ):
        if len(candidates) == 1:
            return candidates[0], None
        if len(candidates) > 1:
            return None, f'"{text.strip()}" could be {", ".join(candidates)}. Type more of the name.'
    return None, f'"{text.strip()}" isn\'t a member yet. Add them under "Add player" first.'


def game_problems(players: list, scores: list) -> list[str]:
    """Same rules the database enforces, checked first so the message is friendlier."""
    problems = []
    if None not in players and len(set(players)) < 4:
        problems.append("A player is listed more than once.")
    if None in scores:
        problems.append("Enter all 4 scores as whole numbers, e.g. 39600.")
    else:
        total = sum(scores)
        if total != GAME_TOTAL:
            problems.append(f"Scores add up to {total:,}, which is {total - GAME_TOTAL:+,} off {GAME_TOTAL:,}.")
        if any(s % 100 for s in scores):
            problems.append("Scores must be multiples of 100.")
    return problems


def game_form(form_key: str, names: list[str], *, play_date: date, table_no: int,
              players: list, scores: list, submit_label: str):
    """Date, table and 4 name/score rows inside one st.form.

    Nothing reruns while typing: type a name, Tab, type a score, Tab ... then submit once.
    Returns (play_date, table_no, players, scores) if submitted and valid, otherwise None.
    """
    with st.form(form_key):
        date_col, table_col = st.columns(2)
        new_date = date_col.date_input("Date", value=play_date, key=f"{form_key}_date")
        new_table = table_col.number_input("Table", min_value=1, step=1, value=table_no, key=f"{form_key}_table")

        typed_names, new_scores = [], []
        for i in range(4):
            name_col, score_col = st.columns([2, 1])
            typed_names.append(name_col.text_input(
                f"Player {i + 1}", value=players[i] or "", placeholder="Name (first letters are enough)",
                key=f"{form_key}_player{i}",
            ))
            new_scores.append(parse_score(score_col.text_input(
                f"Final score {i + 1}", value="" if scores[i] is None else str(scores[i]),
                placeholder="e.g. 39600", key=f"{form_key}_score{i}",
            )))

        st.caption("Members: " + ", ".join(names))
        submitted = st.form_submit_button(submit_label, type="primary")

    if not submitted:
        return None

    new_players, problems = [], []
    for i, typed in enumerate(typed_names):
        name, error = resolve_player(typed, names)
        new_players.append(name)
        if error == "missing":
            problems.append(f"Player {i + 1} is empty.")
        elif error:
            problems.append(f"Player {i + 1}: {error}")
    problems += game_problems(new_players, new_scores)     # report everything at once

    for problem in problems:
        st.error(problem)
    return None if problems else (new_date, int(new_table), new_players, new_scores)


def standings_text(players: list[str], scores: list[int]) -> str:
    order = sorted(zip(scores, players), reverse=True)
    return ", ".join(f"{name} {score:,}" for score, name in order)


def finish_write(message: str) -> None:
    """After a successful write: remember the message, reset the forms, reload data."""
    st.session_state.flash = message
    st.session_state.form_id += 1
    refresh_data()
    st.rerun()


def render_new_game(names: list[str], form_id: int) -> None:
    result = game_form(
        f"new_game_{form_id}", names, play_date=date.today(), table_no=1,
        players=[None] * 4, scores=[None] * 4, submit_label="Save game",
    )
    if result is None:
        return
    play_date, table_no, players, scores = result
    try:
        match_id = call_db_function(
            "SELECT record_game(CAST(:play_date AS date), :table_no, CAST(:players AS text[]), CAST(:scores AS integer[]))",
            {"play_date": play_date, "table_no": table_no, "players": players, "scores": scores},
        )
    except Exception as exc:
        st.error(f"Not saved: {db_error_message(exc)}")
    else:
        finish_write(f"Saved game #{match_id} ({play_date:%b %d}, table {table_no}): {standings_text(players, scores)}.")


def render_edit_game(names: list[str], form_id: int, scores_df: pd.DataFrame) -> None:
    if scores_df.empty:
        st.info("No games recorded yet.")
        return

    games = scores_df.sort_values(["play_date", "match_id", "placement"], ascending=[False, False, True])
    labels = {
        match_id: f"#{match_id} · {g['play_date'].iat[0]:%b %d, %Y} · table {g['table_no'].iat[0]} · "
                  + ", ".join(g["player_name"])
        for match_id, g in games.groupby("match_id", sort=False)
    }
    match_id = st.selectbox(
        "Game to edit (newest first)", list(labels), index=0, format_func=labels.get,
        key=f"edit_pick_{form_id}",
    )
    if match_id is None:
        return

    game = games[games["match_id"] == match_id]
    result = game_form(
        f"edit_{match_id}_{form_id}", names,
        play_date=game["play_date"].iat[0], table_no=int(game["table_no"].iat[0] or 1),
        players=game["player_name"].tolist(), scores=game["score"].astype(int).tolist(),
        submit_label="Save changes",
    )
    if result is not None:
        play_date, table_no, players, scores = result
        try:
            call_db_function(
                "SELECT update_game(:match_id, CAST(:play_date AS date), :table_no, "
                "CAST(:players AS text[]), CAST(:scores AS integer[]))",
                {"match_id": int(match_id), "play_date": play_date, "table_no": table_no,
                 "players": players, "scores": scores},
            )
        except Exception as exc:
            st.error(f"Not saved: {db_error_message(exc)}")
        else:
            finish_write(f"Updated game #{match_id}: {standings_text(players, scores)}.")

    with st.expander("Delete this game"):
        confirmed = st.checkbox(f"Yes, permanently delete game #{match_id}", key=f"confirm_delete_{match_id}_{form_id}")
        if st.button("Delete game", disabled=not confirmed, key=f"delete_{match_id}_{form_id}"):
            try:
                call_db_function("SELECT delete_game(:match_id)", {"match_id": int(match_id)})
            except Exception as exc:
                st.error(f"Not deleted: {db_error_message(exc)}")
            else:
                finish_write(f"Deleted game #{match_id}.")


def render_add_player(form_id: int) -> None:
    with st.form(f"add_player_{form_id}"):
        new_name = st.text_input("New player's name")
        added = st.form_submit_button("Add player", type="primary")    # Enter in the field also submits
    if not added:
        return
    if not new_name.strip():
        st.error("Type a name first.")
        return
    try:
        call_db_function("SELECT add_player(:name)", {"name": new_name})
    except Exception as exc:
        st.error(f"Not added: {db_error_message(exc)}")
    else:
        finish_write(f"Added {new_name.strip()}. They're now in the player lists.")


def render_game_entry(scores_df: pd.DataFrame) -> None:
    if flash := st.session_state.pop("flash", None):
        st.success(flash)

    names = load_player_names()
    form_id = st.session_state.setdefault("form_id", 0)   # bumping this resets the forms

    mode = st.segmented_control(
        "What do you want to do?", ["New game", "Edit a game", "Add player"],
        default="New game", required=True, key="entry_mode",
    )
    if mode == "New game":
        render_new_game(names, form_id)
    elif mode == "Edit a game":
        render_edit_game(names, form_id, scores_df)
    else:
        render_add_player(form_id)

    st.divider()
    if st.button("Lock entry"):
        st.session_state.admin_ok = False
        st.rerun()


# ---------------------------------------------------------------- page

with st.sidebar:
    st.header("🗓️ Mahjong Thursdays")
    st.write("Coming to the next session? Let us know which days you'll attend.")
    st.link_button("RSVP (opens Google Form)", RSVP_FORM_URL, type="primary", use_container_width=True)
    with st.expander("Or fill it in here"):
        st.iframe(f"{RSVP_FORM_URL}?embedded=true", height=700, alt="Mahjong Thursdays RSVP form")

title_col, refresh_col = st.columns([5, 1])
title_col.title("🀄 UM Mahjong League")
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

tab_board, tab_player, tab_games, tab_entry = st.tabs(TABS, key="tab", on_change="rerun")

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
        render_game_entry(scores)
    else:
        render_admin_login()
