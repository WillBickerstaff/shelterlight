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
import numpy as np
import logging
from typing import Optional
from lightlib.db import DB
from lightlib.config import ConfigLoader

def generate_synthetic_days(start_date: dt.date, end_date: dt.date,
                            db: Optional[DB] = None,
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
    all_dates = set(start_date + dt.timedelta(days=i)
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
            df_shifted = _inject_noise(df_shifted, "timestamp",
                                       target_date, jitter_sec)
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

def _inject_noise(df: pd.DataFrame, date_col: str,
                  target_date: dt.date,
                  std_seconds: int) -> pd.DataFrame:
    """Inject random temporal jitter into a timestamp column.

    Adds normally distributed noise (jitter) to the given timestamp column in
    the DataFrame. The amount of jitter is determined by a standard deviation
    in seconds. After jittering, timestamps are clipped to remain within the
    bounds of the target date, ensuring that they do not cross into adjacent
    days. The 'date' column is then updated accordingly based on the new
    timestamps.

    Parameters
    ----------
    df : pd.DataFrame
        The DataFrame containing the timestamp column to be jittered.
    date_col : str
        The name of the timestamp column (e.g., "timestamp") in the DataFrame.
    target_date : datetime.date
        The date to which all jittered timestamps should belong.
    std_seconds : int
        Standard deviation of the jitter to apply, in seconds.

    Returns
    -------
    pd.DataFrame
        A copy of the original DataFrame with the specified timestamp column
        jittered and clipped to the target date, and a recomputed 'date'
        column.

    Notes
    -----
    - This function does not modify the input DataFrame in-place.
    - Returned timestamps are guaranteed to lie within [00:00:00, 23:59:59]
      of the `target_date`.
    - If `df` is empty, it is returned unchanged.
    """
    if df.empty:
        return df.copy()
    jitter = pd.to_timedelta(
            np.random.normal(loc=0, scale=std_seconds, size=len(df)),
            unit="s")
    df[date_col] += jitter

    # Ensure jittered timestamps stay within the bounds of the target day
    day_start = pd.Timestamp(target_date).tz_localize("UTC")
    day_end = day_start + pd.Timedelta(days=1)
    df[date_col] = df[date_col].clip(lower=day_start,
                                     upper=day_end - pd.Timedelta(seconds=1))

    df["date"] = df[date_col].dt.date
    return df

def _find_most_recent_weekday_with_data(
        db: DB, target_date: dt.date) -> Optional[dt.date]:
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
        query, db.get_alchemy_engine(),
        params={"cutoff": target_date.isoformat()})

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
