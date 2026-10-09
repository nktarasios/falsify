-- reference DDL only; never executed (DB-3)
CREATE TABLE users (
  user_id INTEGER,
  signup_date DATE,
  platform VARCHAR,
  country VARCHAR,
  acquisition_source VARCHAR
);
CREATE TABLE events (
  user_id INTEGER,
  event_ts TIMESTAMP,
  event_name VARCHAR,
  platform VARCHAR
);
