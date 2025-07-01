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
- [get_activity_histogram](#get_activity_histogram)
- [get_schedule_accuracy](#get_schedule_accuracy)
- [get_false_negative_rate_by_interval][#get_false_negative_rate_by_interval)
## get_activity_histogram
`get_schedule_accuracy(days_back INTEGER)`

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

## get_schedule_accuracy
`get_schedule_accuracy(days_back INTEGER)`

**Purpose:**\
Summarizes the accuracy of light schedule predictions over the past `days_back` days.

For each day, it reports:

- **True Positives (TP):** lights ON when activity occurred
- **False Positives (FP):** lights ON with no activity
- **False Negatives (FN):** activity occurred but lights were OFF
- **True Negatives (TN):** lights correctly OFF
- **Precision:** TP / (TP + FP)
- **Recall:** TP / (TP + FN)
- **Accuracy:** (TP + TN) / total intervals

**Definition:**

```sql
CREATE OR REPLACE FUNCTION get_schedule_accuracy(days_back INTEGER)
RETURNS TABLE (
    schedule_date DATE,
    true_positives INTEGER,
    false_positives INTEGER,
    false_negatives INTEGER,
    true_negatives INTEGER,
    "precision" NUMERIC(5,2),
    recall NUMERIC(5,2),
    accuracy NUMERIC(5,2)
)
...
```

(*See full definition in \*\***`db_procedures.sql`*)

**Usage:**

```sql
SELECT * FROM get_schedule_accuracy(14);
```

**Example Output:**

| schedule\_date | true\_positives | false\_positives | false\_negatives | true\_negatives | precision | recall | accuracy |
| -------------- | --------------- | ---------------- | ---------------- | --------------- | --------- | ------ | -------- |
| 2025-06-28     | 10              | 2                | 4                | 82              | 0.83      | 0.71   | 0.92     |
| 2025-06-29     | 0               | 0                | 23               | 98              | 0.00      | 0.00   | 0.81     |

**Notes:**

- If no ON predictions were made, precision is reported as `0.00`
- If no actual positives occurred, recall is also `0.00`
- This function helps identify under-predicting or overly cautious models

## get_false_negative_rate_by_interval
`get_false_negative_rate_by_interval(days_back INTEGER)`

**Purpose:**\
Identifies which time intervals most frequently result in false
negatives — where activity occurred but lights were not scheduled ON.

**Definition:**

```sql
CREATE OR REPLACE FUNCTION get_false_negative_rate_by_interval(days_back INTEGER)
RETURNS TABLE (
    interval_number SMALLINT,
    start_time TIME,
    false_negatives INTEGER,
    total_intervals INTEGER,
    fn_rate NUMERIC(5,2)
)
...
```

(*See full definition in **`db_procedures.sql`*)

**Usage:**

```sql
SELECT * FROM get_false_negative_rate_by_interval(30);
```

**Example Output:**

| interval\_number | start\_time | false\_negatives | total\_intervals | fn\_rate |
| ---------------- | ----------- | ---------------- | ---------------- | -------- |
| 22               | 05:30:00    | 18               | 30               | 0.60     |
| 35               | 08:45:00    | 14               | 30               | 0.47     |

**Notes:**

- `start_time` corresponds to the beginning of the interval number in the light schedule grid
- Helps diagnose which specific parts of the day the model consistently misses
- Useful for tuning threshold sensitivity or adding feature context to high-FN intervals