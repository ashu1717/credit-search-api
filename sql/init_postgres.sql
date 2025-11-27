-- init_postgres.sql
-- Creates users, credits, and api_logs tables for the credit-based API

BEGIN;

-- Users table: stores API keys and basic identity
CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  email VARCHAR(255) UNIQUE NOT NULL,
  api_key VARCHAR(64) UNIQUE NOT NULL,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Credits: one row per user, atomic balance
CREATE TABLE IF NOT EXISTS credits (
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  credits_remaining INT NOT NULL DEFAULT 0,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  PRIMARY KEY(user_id)
);

-- API logs: record each request for auditing & billing
CREATE TABLE IF NOT EXISTS api_logs (
  id BIGSERIAL PRIMARY KEY,
  user_id INT REFERENCES users(id),
  endpoint TEXT,
  credits_used INT,
  query_params JSONB,
  execution_time_ms INT,
  client_ip INET,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Optional: index for fast queries by user and created_at
CREATE INDEX IF NOT EXISTS idx_api_logs_user_created_at ON api_logs(user_id, created_at);

COMMIT;
