SELECT CASE WHEN date BETWEEN DATE '2025-02-09' AND DATE '2025-03-10' THEN 'baseline'
            WHEN date BETWEEN DATE '2025-03-23' AND DATE '2025-04-21' THEN 'focus' END AS win,
       channel, count(*) AS n_days, sum(spend) AS total_spend, avg(spend) AS mean_daily_spend
FROM marketing
WHERE date BETWEEN DATE '2025-02-09' AND DATE '2025-04-21'
GROUP BY 1, 2 HAVING win IS NOT NULL ORDER BY 2, 1
