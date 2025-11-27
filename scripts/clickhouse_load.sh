#!/usr/bin/env bash
set -euo pipefail

# This script:
# 1) Starts ClickHouse via docker compose
# 2) Creates DB and table
# 3) Copies parquet into container
# 4) Loads parquet into the table
# 5) Verifies rows

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
PARQUET_PATH="$ROOT_DIR/data/processed/ingested.parquet"

if [[ ! -f "$PARQUET_PATH" ]]; then
  echo "ERROR: Parquet file not found at $PARQUET_PATH" >&2
  exit 1
fi

echo "Starting ClickHouse container..."
docker compose -f "$ROOT_DIR/docker-compose.yml" up -d clickhouse

echo "Waiting for ClickHouse to be healthy..."
for i in {1..30}; do
  STATUS=$(docker inspect -f '{{.State.Health.Status}}' clickhouse 2>/dev/null || echo "unknown")
  if [[ "$STATUS" == "healthy" ]]; then
    echo "ClickHouse is healthy."
    break
  fi
  echo "ClickHouse status: $STATUS (attempt $i)"
  sleep 2
done

if [[ "$STATUS" != "healthy" ]]; then
  echo "ERROR: ClickHouse container is not healthy." >&2
  docker logs clickhouse || true
  exit 1
fi

echo "Creating database 'analytics'..."
docker exec clickhouse clickhouse-client --query "CREATE DATABASE IF NOT EXISTS analytics;"

echo "Creating table 'analytics.persons_ingested'..."
docker exec clickhouse clickhouse-client --multiquery --query "CREATE TABLE IF NOT EXISTS analytics.persons_ingested (
  person_name Nullable(String),
  person_first_name_unanalyzed Nullable(String),
  person_last_name_unanalyzed Nullable(String),
  person_name_unanalyzed_downcase Nullable(String),
  person_title Nullable(String),
  person_functions Nullable(String),
  person_seniority Nullable(String),
  person_email_status_cd Nullable(String),
  person_extrapolated_email_confidence Nullable(String),
  person_email Nullable(String),
  person_phone Nullable(String),
  person_sanitized_phone Nullable(String),
  person_email_analyzed Nullable(String),
  person_linkedin_url Nullable(String),
  person_detailed_function Nullable(String),
  person_title_normalized Nullable(String),
  primary_title_normalized_for_faceting Nullable(String),
  sanitized_organization_name_unanalyzed Nullable(String),
  person_location_city Nullable(String),
  person_location_city_with_state_or_country Nullable(String),
  person_location_state Nullable(String),
  person_location_state_with_country Nullable(String),
  person_location_country Nullable(String),
  person_location_postal_code Nullable(String),
  job_start_date Nullable(String),
  current_organization_ids Nullable(String),
  modality Nullable(String),
  prospected_by_team_ids Nullable(String),
  person_excluded_by_team_ids Nullable(String),
  relavence_boost Nullable(String),
  person_num_linkedin_connections Nullable(String),
  person_location_geojson Nullable(String),
  predictive_scores Nullable(String),
  person_vacuumed_at Nullable(String),
  random Nullable(String),
  \`index\` Nullable(String),
  \`type\` Nullable(String),
  id Nullable(String),
  score Nullable(String)
) ENGINE = MergeTree() ORDER BY id;"

echo "Copying parquet into container..."
docker cp "$PARQUET_PATH" clickhouse:/tmp/ingested.parquet

echo "Loading parquet into table..."
docker exec clickhouse bash -lc "clickhouse-client --query \"INSERT INTO analytics.persons_ingested FORMAT Parquet\" < /tmp/ingested.parquet"

echo "Verifying load..."
docker exec clickhouse clickhouse-client --query "SHOW TABLES FROM analytics;"
docker exec clickhouse clickhouse-client --query "SELECT count() AS rows FROM analytics.persons_ingested;"

echo "Done."