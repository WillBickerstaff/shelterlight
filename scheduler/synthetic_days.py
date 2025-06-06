"""scheduler.synthetic_days.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Generate synthetic days to train the model when it has large gaps
in the data
Author: Will Bickerstaff
Version: 0.2
"""

import datetime as dt
import pandas as pd
from typing import Optional
from lightlib.db import DB
from lightlib.common import ConfigLoader

def generate_synthetic_days(start_date: dt.date, end_date: dt:date],
                            db: Optional[db.DB] = None,
                            interval_minutes: int,
                            target_columns: Optional[list[str]] = None,
                            activity_only: bool = True) -> pd.DataFrame:

    """Generate synthetic training data for missing activity days.

    When the system is offline or activity is not recorded, model training
    suffers due to missing recent patterns. This function fills those gaps by
    finding past days with the same weekday and copying their interval-level
    structure. It realigns dates and optionally injects light noise to reduce
    overfitting.

    A fallback to a default DB engine is used if one is not provided.

    Parameters
    ----------
    start_date : dt.date
        The date to commence synthetic generation for. Any days without
        activity and before `end_date` will have synthetic data created.
    end_date : dt_date
        The last date for which synthetic date could be generated.
    engine : sqlalchemy.engine.Engine, optional
        SQLAlchemy engine to use for querying past interval and schedule data.
        If not provided, a default engine from lightlib.db.DB is used.
    interval_minutes : int
        Duration of each time interval used in the system (e.g., 10 for
        10-minute intervals).
    target_columns : list[str]
        List of feature columns required for model training. The output
        DataFrame will match this structure to ensure compatibility.
    activity_only : bool, optional (default=True)
        If True, only activity logs will be synthesised. If False, historical
        schedule accuracy values may also be approximated.

    Returns
    -------
    pd.DataFrame
        A DataFrame containing synthetic training rows for the missing dates.
        Includes columns for all required training features, plus an
        `is_synthetic` flag set to True.
    """
    if not ConfigLoader().synth_days:
        return pd.DataFrame()
    
    if db is None:
        db = DB()

    # Identify which days already have activity
    query = """
        SELECT DISTINCT DATE(timestamp) AS date
        FROM activity_log
        WHERE activity_pin > 0
            AND timestamp >= %(start)s AND timestamp < %(end)s
    """
    engine = db.get_alchemy_engine()
    existing = pd.read_sql_query(query, engine, params={
        "start": start_date.isoformat(),
        "end": (end_date + dt.timedelta(days=1)).isoformat()}
                                 )["date"].tolist()

    # Convert to set of datetime
    existing_dates = set(pd.to_datetime(existing).date)

    # Build the full range and remove the existing days with activity
    all_dates = set(start_date + dt.timedelta(days=1)
                    for i in range((end_date - start_date).days + 1))
    missing_dates = sorted(all_dates - existing_dates)

    if not missing_dates:
        # No synthetic generation needed
        logging.info("No days missing activity between %s and %s",
                     start_date, end_date)
        return pd.DataFrame()

    synthetic_rows = []
    inject_noise = ConfigLoader().inject_synth_noise
    jitter_sec = ConfigLoader().synth_noise_seconds
    for target_date in missing_dates:
        # For each missing day find a recent match
        matched_day = _find_most_recent_weekday_with_data(
            db=db, target_date=target_date)
        if matched_day is None:
            # No usable historic day for this weekday
            logging.debug("No historic match for %s", target_date)
            continue

        # Load & shift activity to the missing day
        df_original = db.load_activity_for_date(matched_day)
        df_shifted = _shift_activity_to_date(
            df_original, source_date=matched_day, target_date=target_date)
        df_shifted["is_synthetic"] = True
        if inject_noise:
            jitter = pd.to_timedelta(np.random.normal(loc=0, scale=jitter_sec,
                                                      size=len(df_shifted)),
                                     unit="s")
        df_shifted["timestamp"] += jitter

        synthetic_rows.append(df_shifted)

    if not synthetic_rows:
        # No synthetic days generated
        return pd.DataFrame()

    # Concatenate all synthetic rows
    df_final = pd.concat(synthetic_rows, ignore_index=True)

    # Match column format if given
    if target_columns:
        for col in target_columns:
            if col not in df_final.columns:
                df_final[col] = None # Pad missing columns with Nulls
        df_final = df_final[target_columns + ["is_synthetic"]]

    return df_final

def _find_most_recent_weekday_with_data(
        db: db.DB, target_date: dt.date) -> Optional[dt.date]:
    """Find the most recent date before `target_date` with activity data.

    Looks for days in the activity log that match the same weekday and have
    contain activity data.

    Args:
    -----
    target_date: datetime.date
        The date for which we want to replicate a synthetic day.
    engine: sqlalchemy.engine.Engine
        SQLAlchemy engine to access the activity_log table.

    Returns
    -------
    Optional[datetime.date]
        The most recent suitable date before target_date, None if nothing is
        found.
    """
    weekday = target_date.weekday()

    query = """
        SELECT DATE(timestamp) AS date
        FROM activity_log
        WHERE activity_pin > 0
            AND timestamp < %(cutoff)s
        GROUP BY date
        ORDER BY date DESC
    """

    df= pd.read_sql_query(
        query, engine, params={"cutoff": target_date.isoformate()})

    if df.empty:
        return None

    # Add a column with the weekday number (0=Mon... 6=Sun)
    df["weekday"] = df["date"].apply(lambda d: d.weekday())
    # Filter rows that match the target_date weekday
    matches = df[df["weekday"] == weekday]
    if matches.empty:
        return None

    # Return the first match (most recent)
    return matches.iloc[0]["date"]


def _shift_activity_to_date(df: pd.DataFrame, source_date: dt.date,
                            target_date: dt.date) -> pd.DataFrame:
    """Adjust timestamps in the DataFrame from source_date to target_date.

    Preserves time-of-day while adjusting the calendar date. Ignores rows
    where the timestamp does not fall on the source date.

    Args:
    -----
    df: pd.DataFrame
        DataFrame containing at least a 'timestamp' column with datetime
        values.
    source_date: datetime.date
        The original date of the activity data.
    target_date: datetime.date
        The date to shift the activity to.
    """
    if df.empty:
        return df.copy()
    # Ensure 'timestamp' is datetime and filter correct 'source_date'
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df[df["timestamp"].notna() & (df["timestamp"].dt.date == source_date)]

    # Determine offset in days
    delta = target_date - source_date
    df["timestamp"] = df["timestamp"] + pd.to_timedelta(delta)

    return df
