WITH grid AS (
  SELECT CAST(d AS DATE) AS day, g.is_ios
  FROM range(TIMESTAMP '2025-03-22', TIMESTAMP '2025-04-22', INTERVAL 1 DAY) t(d)
  CROSS JOIN (SELECT 0 AS is_ios UNION ALL SELECT 1) g
),
daily AS (
  SELECT CAST(event_ts AS DATE) AS day,
         CASE WHEN platform = 'ios' THEN 1 ELSE 0 END AS is_ios,
         count(*) AS n_sessions
  FROM events
  WHERE event_name = 'session_start'
    AND event_ts >= TIMESTAMP '2025-03-22' AND event_ts < TIMESTAMP '2025-04-22'
  GROUP BY 1, 2
),
filled AS (
  SELECT g.day, g.is_ios, coalesce(d.n_sessions, 0) AS n_sessions
  FROM grid g LEFT JOIN daily d ON d.day = g.day AND d.is_ios = g.is_ios
),
pre AS (
  SELECT is_ios, avg(n_sessions) AS pre_mean FROM filled
  WHERE day BETWEEN DATE '2025-03-22' AND DATE '2025-04-04' GROUP BY is_ios
)
SELECT f.day, f.is_ios, f.n_sessions, f.n_sessions / p.pre_mean AS idx,
       CASE WHEN f.day BETWEEN DATE '2025-03-22' AND DATE '2025-04-04' THEN 0
            WHEN f.day BETWEEN DATE '2025-04-05' AND DATE '2025-04-18' THEN 1 END AS post
FROM filled f JOIN pre p ON p.is_ios = f.is_ios
WHERE f.day BETWEEN DATE '2025-03-22' AND DATE '2025-04-18'
ORDER BY f.day, f.is_ios
