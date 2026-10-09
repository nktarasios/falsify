WITH ret AS (
  SELECT u.user_id, u.platform,
    CASE WHEN u.signup_date BETWEEN DATE '2025-02-09' AND DATE '2025-03-10' THEN 'baseline'
         WHEN u.signup_date BETWEEN DATE '2025-03-23' AND DATE '2025-04-21' THEN 'focus' END AS win,
    MAX(CASE WHEN e.event_name IN ('session_start', 'session_started')
              AND date_diff('day', u.signup_date, CAST(e.event_ts AS DATE)) BETWEEN 7 AND 13
             THEN 1 ELSE 0 END) AS d7
  FROM users u LEFT JOIN events e ON e.user_id = u.user_id
  WHERE u.signup_date BETWEEN DATE '2025-02-09' AND DATE '2025-04-21'
  GROUP BY u.user_id, u.platform, u.signup_date
)
SELECT win, count(*) AS n, sum(d7) AS retained, avg(d7) AS d7_rate,
       sum(CASE WHEN platform = 'ios' THEN d7 END) AS ios_retained,
       sum(CASE WHEN platform = 'ios' THEN 1 ELSE 0 END) AS ios_n
FROM ret WHERE win IS NOT NULL GROUP BY win ORDER BY win
