"""scheduler.synthetic_days.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Generate synthetic days to train the model when it has large gaps
in the data
Author: Will Bickerstaff
Version: 0.2
"""

import sqlalchemy
import datetime as dt
import pandas as pd
from typing import Optional

def generate_synthetic_days(missing_dates: list[dt.date],
                            engine: Optional[sqlalchemy.engine.Engine] = None,
                            interval_minutes: int,
                            target_columns: list[str],
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
    missing_dates : list[datetime.date]
        List of target dates that had no recorded activity and need synthetic
        interval data.
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


def _find_most_recent_weekday_with_data(
        engine Optional[sqlalchemy.engine.Engine] = None,
        target_date: dt.date,
        interval_minutes: int) -> Optional[dt.date]:
    """Search backwards in time for a past day that:

    - Matches the same weekday as `target_date`
    - Contains activity data in `activity_log`
    """
    pass


def _load_activity_for_date(engine Optional[sqlalchemy.engine.Engine] = None,
                            date: dt.date) -> pd.DataFrame:
    """Load activity data for a specific date from the activity_log table.

    Should return a DataFrame with at least ['timestamp', 'activity_pin'].
    """
    pass


def _shift_activity_to_date(df: pd.DataFrame, source_date: dt.date,
                            target_date: dt.date,
                            interval_minutes: int) -> pd.DataFrame:
    """Adjust timestamps in the DataFrame from source_date to target_date."""
    pass

def _inject_noise(df: pd.DataFrame,
                  numeric_cols: Optional[list[str]] = None,
                  std_dev: float = 0.05) -> pd.DataFrame:
    """Add Gaussian noise to numerical feature cols to prevent overfitting."""
    pass
