# Stored Procedures for Shelter Lighting Control Database

Stored procedures are defined in `db_procedures.sql`,
located in the `lightlib/` directory. These procedures are automatically
applied during database initialization to support analytics and reporting.

---

## Overview

Stored procedures are created in PostgreSQL using standard SQL syntax and
provide reusable server-side logic for querying activity and light scheduling
data.

These procedures are installed automatically if the database is set up during
the application's first run.

---

## Available Procedures

### `get_activity_histogram(days_back INTEGER)`

**Purpose:**
Returns a histogram of activity detections per day for the most recent
`days_back` days.

**Definition:**

```sql
CREATE OR REPLACE FUNCTION get_activity_histogram(days_back INTEGER)
RETURNS TABLE (
    activity_date DATE,
    detections INTEGER
)
LANGUAGE SQL
AS $$
    SELECT
        DATE(timestamp) AS activity_date,
        COUNT(*) AS detections
    FROM
        activity_log
    WHERE
        timestamp >= CURRENT_DATE - INTERVAL '1 day' * days_back
    GROUP BY
        DATE(timestamp)
    ORDER BY
        DATE(timestamp);
$$;```

**Usage**
From the postgres command line when connected to the `activity_db` database:
```sql
SELECT * FROM get_activity_histogram(14);```

Returns a table containg the activity counts for the last 14 days:

| activity_date | detections |
| ------------- | ---------- |
| 2025-06-17    | 375        |
| 2025-06-18    | 333        |
| 2025-06-19    | 320        |
| ...           | ...        |