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
