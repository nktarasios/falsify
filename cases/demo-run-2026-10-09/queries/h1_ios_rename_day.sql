SELECT CAST(event_ts AS DATE) AS day, event_name, count(*) AS n
FROM events
WHERE platform = 'ios' AND event_name IN ('session_start', 'session_started')
  AND event_ts >= TIMESTAMP '2025-03-23' AND event_ts < TIMESTAMP '2025-04-22'
GROUP BY 1, 2 ORDER BY 1, 2
