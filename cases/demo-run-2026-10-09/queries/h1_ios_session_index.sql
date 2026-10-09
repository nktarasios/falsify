WITH daily AS (
  SELECT CAST(event_ts AS DATE) AS day,
         CASE WHEN platform = 'ios' THEN 1 ELSE 0 END AS is_ios,
         count(*) AS n
  FROM events
  WHERE event_name = 'session_start'
    AND event_ts >= TIMESTAMP '2025-03-22' AND event_ts < TIMESTAMP '2025-04-22'
  GROUP BY 1, 2
),
pre AS (
  SELECT is_ios, avg(n) AS pre_mean FROM daily
  WHERE day BETWEEN DATE '2025-03-22' AND DATE '2025-04-04' GROUP BY is_ios
)
SELECT d.day, d.is_ios, d.n, d.n / p.pre_mean AS idx,
       CASE WHEN d.day BETWEEN DATE '2025-03-22' AND DATE '2025-04-04' THEN 0
            WHEN d.day BETWEEN DATE '2025-04-05' AND DATE '2025-04-18' THEN 1 END AS post
FROM daily d JOIN pre p ON p.is_ios = d.is_ios
WHERE d.day BETWEEN DATE '2025-03-22' AND DATE '2025-04-21'
ORDER BY d.day, d.is_ios
