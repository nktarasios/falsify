WITH ret AS (
  SELECT u.user_id, u.signup_date, u.platform, u.acquisition_source,
    MAX(CASE WHEN e.event_name = 'session_start'
              AND date_diff('day', u.signup_date, CAST(e.event_ts AS DATE)) BETWEEN 7 AND 13
             THEN 1 ELSE 0 END) AS d7
  FROM users u LEFT JOIN events e ON e.user_id = u.user_id
  WHERE u.signup_date BETWEEN DATE '2025-02-09' AND DATE '2025-04-21'
  GROUP BY u.user_id, u.signup_date, u.platform, u.acquisition_source
)
SELECT platform,
       CASE WHEN signup_date BETWEEN DATE '2025-03-08' AND DATE '2025-03-21' THEN 'pre'
            WHEN signup_date BETWEEN DATE '2025-04-04' AND DATE '2025-04-17' THEN 'post' END AS grp,
       count(*) AS n, sum(d7) AS retained, avg(d7) AS d7_rate
FROM ret
WHERE platform IN ('android', 'web')
  AND (signup_date BETWEEN DATE '2025-03-08' AND DATE '2025-03-21'
       OR signup_date BETWEEN DATE '2025-04-04' AND DATE '2025-04-17')
GROUP BY 1, 2 ORDER BY 1, 2
