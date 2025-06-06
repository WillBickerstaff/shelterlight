"""lightlib.db.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Management and connection to the database
Author: Will Bickerstaff
Version: 0.1
"""

import logging
import psycopg2
import time
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from lightlib.config import ConfigLoader
from typing import Optional, Tuple, List


class DB:
    """Manage PostgreSQL database connections, set up db tables and indexes.

    Attributes
    ----------
        _db_host (str): Database host address.
        _db_port (int): Port number for database connection.
        _db_database (str): Database name.
        _db_user (str): Username for database authentication.
        _db_password (str): Password for database authentication.
        _db_retry (int): Number of retry attempts for database connection.
        _db_retry_delay (int): Delay between retry attempts.
        _conn (psycopg2.connect): The PostgreSQL database connection object.
    """

    def __init__(self, config_section: str = "ACTIVITY_DB"):
        """
        Initialize the DB instance with database configuration.

        Args
        ----
            config_section (str): The configuration section name for database
            settings.
        """
        config_loader = ConfigLoader()
        self._db_host = config_loader.get_config_value(
            config_loader.config, config_section, "host")
        self._db_port = int(config_loader.get_config_value(
            config_loader.config, config_section, "port"))
        self._db_database = config_loader.get_config_value(
            config_loader.config, config_section, "database")
        self._db_user = config_loader.get_config_value(
            config_loader.config, config_section, "user")
        self._db_password = config_loader.get_config_value(
            config_loader.config, config_section, "password")
        self._db_retry = int(config_loader.get_config_value(
            config_loader.config, config_section, "connect_retry"))
        self._db_retry_delay = int(config_loader.get_config_value(
            config_loader.config, config_section, "connect_retry_delay"))
        self._conn = self._connect_to_db()
        self._setup_database()
        self._alchemy_engine = None
        self._alchemy_exists = True

    @property
    def conn(self) -> psycopg2.extensions.connection:
        """
        Connection property to access the active database connection.

        Returns
        -------
            psycopg2.extensions.connection: The PostgreSQL connection object.
        """
        return self._conn

    def _connect_to_db(self) -> psycopg2.extensions.connection:
        """
        Establish a connection to the PostgreSQL database with retry logic.

        Returns
        -------
            psycopg2.extensions.connection: Database connection object.

        Raises
        ------
            psycopg2.DatabaseError: If connection fails after all retry
                attempts.
        """
        for attempt in range(self._db_retry):
            try:
                connection = psycopg2.connect(
                    host=self._db_host,
                    port=self._db_port,
                    database=self._db_database,
                    user=self._db_user,
                    password=self._db_password
                )
                logging.info("Connected to PostgreSQL database successfully.")
                return connection
            except psycopg2.DatabaseError as e:
                logging.error(
                    "Failed to connect to PostgreSQL database: %s", e)
                if attempt < self._db_retry - 1:
                    time.sleep(self._db_retry_delay)
                    logging.info(
                        "Retrying connection attempt %d...", attempt + 1)
                else:
                    raise

    def _setup_database(self) -> None:
        """Initialize db tables & indexes for activity logs & light scheduling.

        Executes SQL commands to create:
        1. `activity_log` table with timestamp index
        2. `light_schedules` table with date and interval indexes
        3. Update trigger for light_schedules

        All integer fields in activity_log are SMALLINT to reduce storage.
        SMALLINT holds value from -32768 to +32767 (+32767 is 9 hrs, 6 min)
        """
        # Activity Log table
        create_activity_table = """
            CREATE TABLE IF NOT EXISTS activity_log (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMPTZ NOT NULL,
                day_of_week SMALLINT NOT NULL,
                month SMALLINT NOT NULL,
                year SMALLINT NOT NULL,
                duration SMALLINT NOT NULL,
                activity_pin SMALLINT NOT NULL
            );
        """
        create_activity_index = """
            CREATE INDEX IF NOT EXISTS idx_activity_timestamp
            ON activity_log (timestamp);
        """

        # Light Schedules table
        create_schedules_table = """
            CREATE TABLE IF NOT EXISTS light_schedules (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL,
                interval_number SMALLINT NOT NULL,
                start_time TIME NOT NULL,
                end_time TIME NOT NULL,
                prediction BOOLEAN NOT NULL,
                was_correct BOOLEAN,
                false_positive BOOLEAN DEFAULT FALSE,
                false_negative BOOLEAN DEFAULT FALSE,
                confidence DECIMAL(5,4),
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT valid_confidence CHECK (confidence >= 0 AND
                                                   confidence <= 1),
                CONSTRAINT unique_schedule_interval UNIQUE (
                    date, interval_number)
            );
        """
        create_schedules_indexes = """
            CREATE INDEX IF NOT EXISTS idx_light_schedules_date
            ON light_schedules(date);
            CREATE INDEX IF NOT EXISTS idx_light_schedules_interval
            ON light_schedules(interval_number);
        """

        # Update trigger for light_schedules
        create_update_trigger_func = """
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ language 'plpgsql';
        """

        create_trigger = """
            DROP TRIGGER IF EXISTS update_light_schedules_updated_at ON
                light_schedules;
            CREATE TRIGGER update_light_schedules_updated_at
                BEFORE UPDATE ON light_schedules
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column();
        """

        # Execute all setup queries within a cursor context
        with self._conn.cursor() as cursor:
            cursor.execute(create_activity_table)
            cursor.execute(create_activity_index)
            cursor.execute(create_schedules_table)
            cursor.execute(create_schedules_indexes)
            cursor.execute(create_update_trigger_func)
            cursor.execute(create_trigger)
            self._conn.commit()

        logging.info("Activity and Light Schedules databases and indexes "
                     "initialized successfully.")

    def close_connection(self) -> None:
        """
        Close the database connection gracefully.

        Ensures the connection is closed to release resources.
        """
        if self._conn:
            self._conn.close()
            logging.info("Database connection closed.")

    def query(self, query: str, params: Optional[Tuple] = None,
              fetch: bool = False) -> Optional[List[Tuple]]:
        """
        Execute SQL query with optional parameters, optionally fetch results.

        Args
        ----
            query (str): The SQL query to execute.
            params (tuple, optional): Parameters to safely pass into the query.
            fetch (bool, optional): Whether to fetch and return query results.

        Returns
        -------
            list: Query results if fetch is True; otherwise, None.

        Raises
        ------
            psycopg2.DatabaseError: If there is an error executing the query.
        """
        try:
            with self._conn.cursor() as cursor:
                # Execute the query with provided parameters
                cursor.execute(query, params)
                # Fetch results if specified
                result = cursor.fetchall() if fetch else None
                # Commit the transaction if successful
                self._conn.commit()
                logging.debug("Query executed successfully.")
                return result
        except psycopg2.DatabaseError as e:
            # Rollback on error to maintain database consistency
            self._conn.rollback()
            logging.error("Query execution failed: %s", e)
            raise

    def get_alchemy_engine(self):
        """Return an SQLAlchemy engine or fallback to None on failure."""
        if self._alchemy_engine is None and self._alchemy_exists:
            try:
                uri = f"postgresql://{self._db_user}:{self._db_password}" \
                      f"@{self._db_host}:{self._db_port}/{self._db_database}"
                self._alchemy_engine = create_engine(uri)
            except (ImportError, SQLAlchemyError) as e:
                logging.warning("Failed to create SQLAlchemy engine: %s", e)
                self._alchemy_exists = False
                self._alchemy_engine = None
        return self._alchemy_engine

    def load_activity_for_date(self, date: dt.date) -> pd.DataFrame:
        """Load all activity data for a specific date.

        Queries the activity_log table for rows falling within the given day.

        Args:
        ----
        date: datetime.date
            The specific date to retrieve interval activity for.

        Returns:
        -------
        pd.DataFrame
            DataFrame of interval data for the date, with all columns
        """
        start = dt.datettime.combine(date, dt.time.min)
        end = dt.datetime.combine(date = dt.timedelta(days=1), dt.time.min)

        query = """
            SELECT *
            FROM activity_log
            WHERE timestamp >= :start AND timestamp < :end
            ORDER BY timestamp ASC
        """

        return pd.read_sql_query(quer, self.engine, params={
            "start": start.isoformat(),
            "end": end.isoformat()}).sort_values("timestamp")

    def __del__(self):
        """Destructor to ensure connection is closed on deletion of the DB."""
        self.close_connection()
