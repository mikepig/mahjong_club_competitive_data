"""Database connection for Python scripts and notebooks.

Reads DATABASE_URL from a .env file (see .env.example), so the password never lives in code.

    from db import get_engine
    import pandas as pd
    df = pd.read_sql("SELECT * FROM leaderboard", get_engine())
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

load_dotenv()


def get_engine() -> Engine:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env and fill it in.")
    return create_engine(url)
