SELECT platform, event_name,
       CASE WHEN event_ts < TIMESTAMP '2025-04-05' THEN 'before' ELSE 'on_after' END AS side,
       count(*) AS n
FROM events
WHERE event_ts >= TIMESTAMP '2025-03-22' AND event_ts < TIMESTAMP '2025-04-22'
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3
