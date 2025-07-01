-- Function: get_activity_histogram
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
        activity_date
    ORDER BY
        activity_date;
$$;

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
LANGUAGE SQL
AS $$
    SELECT
        date AS schedule_date,
        SUM(CASE WHEN prediction AND NOT false_positive
	    AND NOT false_negative THEN 1 ELSE 0 END) AS true_positives,
        SUM(CASE WHEN prediction AND false_positive THEN 1 ELSE 0 END)
	    AS false_positives,
	SUM(CASE WHEN NOT prediction AND false_negative THEN 1 ELSE 0 END)
	    AS false_negatives,
	SUM(CASE WHEN NOT prediction AND NOT false_negative THEN 1 ELSE 0 END)
	    AS true_negatives,
	ROUND(CASE WHEN SUM(CASE WHEN prediction THEN 1 ELSE 0 END) = 0 THEN 0
	    ELSE SUM(CASE WHEN prediction AND NOT false_positive
	             AND NOT false_negative THEN 1 ELSE 0 END) * 1.0
		     / NULLIF(SUM(CASE WHEN prediction THEN 1 ELSE 0 END), 0)
		     END, 2) AS "precision",
	ROUND(CASE WHEN SUM(CASE WHEN NOT prediction AND false_negative
	                    THEN 1 ELSE 0 END) +
		SUM(CASE WHEN prediction AND NOT false_positive
		    AND NOT false_negative THEN 1 ELSE 0 END) = 0 THEN 0
		    ELSE SUM(CASE WHEN prediction AND NOT false_positive
		    AND NOT false_negative THEN 1 ELSE 0 END) * 1.0
		    / NULLIF(SUM(CASE WHEN NOT prediction AND false_negative
		    THEN 1 ELSE 0 END) + SUM(CASE WHEN prediction
		    AND NOT false_positive AND NOT false_negative
		    THEN 1 ELSE 0 END), 0)END, 2) AS recall,
	ROUND(CASE WHEN COUNT(*) = 0 THEN 0 ELSE (SUM(CASE WHEN prediction AND
	      NOT false_positive AND NOT false_negative THEN 1 ELSE 0 END) +
	      SUM(CASE WHEN NOT prediction AND NOT false_negative THEN 1
	      ELSE 0 END)) * 1.0 / COUNT(*)END, 2) AS accuracy
    FROM light_schedules
    	 WHERE date >= CURRENT_DATE - INTERVAL '1 day' * days_back
	 GROUP BY date
	 ORDER BY date;
$$;

CREATE OR REPLACE FUNCTION get_false_negative_rate_by_interval(
       days_back INTEGER)
RETURNS TABLE (
    interval_number SMALLINT,
    start_time TIME,
    false_negatives INTEGER,
    total_intervals INTEGER,
    fn_rate NUMERIC(5,2)
)
LANGUAGE SQL
AS $$
    SELECT
        interval_number,
	MIN(start_time) AS start_time,
        SUM(CASE WHEN false_negative THEN 1 ELSE 0 END) AS false_negatives,
	COUNT(*) AS total_intervals,
	ROUND(SUM(CASE WHEN false_negative THEN 1 ELSE 0 END)::NUMERIC /
	      NULLIF(COUNT(*), 0), 2) AS fn_rate
    FROM light_schedules
    WHERE date >= CURRENT_DATE - INTERVAL '1 day' * days_back
    GROUP BY interval_number
    ORDER BY fn_rate DESC;
$$;

CREATE OR REPLACE FUNCTION get_false_positive_rate_by_interval(
       days_back INTEGER)
RETURNS TABLE (
    interval_number SMALLINT,
    start_time TIME,
    false_positives INTEGER,
    total_intervals INTEGER,
    fp_rate NUMERIC(5,2)
)
LANGUAGE SQL
AS $$
    SELECT
        interval_number,
        MIN(start_time) AS start_time,
        SUM(CASE WHEN false_positive THEN 1 ELSE 0 END) AS false_positives,
        COUNT(*) AS total_intervals,
        ROUND(SUM(CASE WHEN false_positive THEN 1 ELSE 0 END)::NUMERIC
	/ NULLIF(COUNT(*), 0), 2) AS fp_rate
    FROM light_schedules
    WHERE date >= CURRENT_DATE - INTERVAL '1 day' * days_back
    GROUP BY interval_number
    ORDER BY fp_rate DESC;
$$;

CREATE OR REPLACE FUNCTION get_confidence_distribution(days_back INTEGER)
RETURNS TABLE (
    confidence_bin TEXT,
    interval_count INTEGER
)
LANGUAGE SQL
AS $$
    SELECT
        CASE
            WHEN confidence < 0.2 THEN '0.0–0.2'
            WHEN confidence < 0.4 THEN '0.2–0.4'
            WHEN confidence < 0.6 THEN '0.4–0.6'
            WHEN confidence < 0.8 THEN '0.6–0.8'
            ELSE '0.8–1.0'
        END AS confidence_bin,
        COUNT(*) AS interval_count
    FROM light_schedules
    WHERE date >= CURRENT_DATE - INTERVAL '1 day' * days_back
    	  AND confidence IS NOT NULL
    GROUP BY confidence_bin
    ORDER BY confidence_bin;
$$;

CREATE OR REPLACE FUNCTION get_daily_on_intervals(days_back INTEGER)
RETURNS TABLE (
    schedule_date DATE,
    on_intervals INTEGER
)
LANGUAGE SQL
AS $$
    SELECT
        date AS schedule_date,
        COUNT(*) FILTER (WHERE prediction = TRUE) AS on_intervals
        FROM light_schedules
    WHERE date >= CURRENT_DATE - INTERVAL '1 day' * days_back
    GROUP BY date
    ORDER BY date;
$$;

CREATE OR REPLACE FUNCTION get_daily_off_intervals(days_back INTEGER)
RETURNS TABLE (
    schedule_date DATE,
    off_intervals INTEGER
)
LANGUAGE SQL
AS $$
    SELECT
       date AS schedule_date,
       COUNT(*) FILTER (WHERE prediction = FALSE) AS off_intervals
    FROM light_schedules
    WHERE date >= CURRENT_DATE - INTERVAL '1 day' * days_back
    GROUP BY date
    ORDER BY date;
$$;
