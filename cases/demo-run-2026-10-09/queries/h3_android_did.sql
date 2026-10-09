WITH ret AS (
  SELECT u.user_id, u.signup_date, u.platform, u.acquisition_source,
    MAX(CASE WHEN e.event_name = 'session_start'
              AND date_diff('day', u.signup_date, CAST(e.event_ts AS DATE)) BETWEEN 7 AND 13
             THEN 1 ELSE 0 END) AS d7
  FROM users u LEFT JOIN events e ON e.user_id = u.user_id
  WHERE u.signup_date BETWEEN DATE '2025-02-09' AND DATE '2025-04-21'
  GROUP BY u.user_id, u.signup_date, u.platform, u.acquisition_source
)
SELECT signup_date,
       CASE WHEN platform = 'android' THEN 1 ELSE 0 END AS is_android,
       CASE WHEN signup_date BETWEEN DATE '2025-03-23' AND DATE '2025-04-21' THEN 1 ELSE 0 END AS focus,
       count(*) AS n, avg(d7) AS d7_rate
FROM ret
WHERE platform IN ('android', 'web')
  AND (signup_date BETWEEN DATE '2025-02-09' AND DATE '2025-03-10'
       OR signup_date BETWEEN DATE '2025-03-23' AND DATE '2025-04-21')
GROUP BY 1, 2, 3 ORDER BY 1, 2
