SELECT platform, count(*) AS n
FROM events
WHERE event_ts BETWEEN '2025-03-01' AND '2025-04-30'
GROUP BY platform
