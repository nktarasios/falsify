WITH ret AS (
  SELECT u.user_id, u.signup_date, u.platform, u.country, u.acquisition_source,
    CASE WHEN u.signup_date BETWEEN DATE '2025-02-09' AND DATE '2025-03-10' THEN 'baseline'
         WHEN u.signup_date BETWEEN DATE '2025-03-23' AND DATE '2025-04-21' THEN 'focus' END AS win,
    MAX(CASE WHEN e.event_name = 'session_start'
              AND date_diff('day', u.signup_date, CAST(e.event_ts AS DATE)) BETWEEN 7 AND 13
             THEN 1 ELSE 0 END) AS d7
  FROM users u LEFT JOIN events e ON e.user_id = u.user_id
  WHERE u.signup_date BETWEEN DATE '2025-02-09' AND DATE '2025-04-21'
  GROUP BY u.user_id, u.signup_date, u.platform, u.country, u.acquisition_source
)
SELECT win, acquisition_source AS segment, count(*) AS n, sum(d7) AS retained, avg(d7) AS d7_rate
FROM ret WHERE win IS NOT NULL AND platform <> 'ios' GROUP BY win, acquisition_source ORDER BY segment, win
