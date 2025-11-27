# Sample Outputs (Consolidated)

This document consolidates the captured outputs from `docs/outputs/` for easy review and submission.


## Health

File: `docs/outputs/health.json`

```
{
  "ok": true,
  "postgres": true,
  "redis": true,
  "clickhouse": true
}
```

## Search

File: `docs/outputs/search.json`

```
{
  "results": [
    {
      "id": "54a543a27468692cf0421f8a",
      "person_name": "$Sethiya Matram",
      "person_title": "MANAGER",
      "person_email": null,
      "score": "1"
    },
    {
      "id": "5570a7b173696426d5631a00",
      "person_name": "'Jay' Jeffrey",
      "person_title": "Manager of Customer Operations II",
      "person_email": "jay@blackboxresale.com",
      "score": "1"
    },
    {
      "id": "5ad22bb0a6da9884c56e03a8",
      "person_name": "'Modern Blomquist",
      "person_title": "Sales Manager",
      "person_email": null,
      "score": "1"
    },
    {
      "id": "54a6e41b746869622036ab01",
      "person_name": "???-Milly",
      "person_title": "Project Manager",
      "person_email": null,
      "score": "1"
    },
    {
      "id": "54a18a3e74686978ad316000",
      "person_name": "????Tt?? ?Ocks??",
      "person_title": "Merchandising Manager",
      "person_email": null,
      "score": "1"
    }
  ],
  "count": 5,
  "total_records": 27441,
  "page": 1,
  "limit": 5,
  "credits_used": 1,
  "exec_ms": 60
}
```

## Person

File: `docs/outputs/person.json`

```
{
  "record": {
    "person_name": "$Sethiya Matram",
    "person_first_name_unanalyzed": "$sethiya",
    "person_last_name_unanalyzed": "matram",
    "person_name_unanalyzed_downcase": "$sethiya matram",
    "person_title": "MANAGER",
    "person_functions": null,
    "person_seniority": "manager",
    "person_email_status_cd": "Unavailable",
    "person_extrapolated_email_confidence": null,
    "person_email": null,
    "person_phone": null,
    "person_sanitized_phone": null,
    "person_email_analyzed": null,
    "person_linkedin_url": "http://www.linkedin.com/in/sethiya-matram-5501263a",
    "person_detailed_function": "manager",
    "person_title_normalized": "manager",
    "primary_title_normalized_for_faceting": "Manager",
    "sanitized_organization_name_unanalyzed": "north delhi power limited",
    "person_location_city": "New Delhi",
    "person_location_city_with_state_or_country": "New Delhi, India",
    "person_location_state": "Delhi",
    "person_location_state_with_country": "Delhi, India",
    "person_location_country": "India",
    "person_location_postal_code": null,
    "job_start_date": null,
    "current_organization_ids": "['54a1298d69702db878907701']",
    "modality": "people",
    "prospected_by_team_ids": null,
    "person_excluded_by_team_ids": null,
    "relavence_boost": "-0.13068528194400547",
    "person_num_linkedin_connections": "1",
    "person_location_geojson": "{'type': 'envelope', 'coordinates': [[77.076779, 28.6885801], [77.1028819, 28.682611]]}",
    "predictive_scores": null,
    "person_vacuumed_at": "2017-09-01T03:15:04.000+00:00",
    "random": "0.5406352600247862",
    "index": "people_v7",
    "type": "person",
    "id": "54a543a27468692cf0421f8a",
    "score": "1"
  },
  "exec_ms": 134
}
```

## Admin Topup

File: `docs/outputs/topup.json`

```
{
  "ok": true,
  "user_id": 1,
  "added": 10,
  "balance": 90
}
```

## Credits (Postgres) — Before

File: `docs/outputs/credits_before.txt`

```
user_id | credits_remaining 
---------+-------------------
       1 |                87
(1 row)

... (interactive terminal control sequences preserved) ...
```

## Credits (Postgres) — After

File: `docs/outputs/credits_after.txt`

```
user_id | credits_remaining 
---------+-------------------
       1 |                86
(1 row)

... (interactive terminal control sequences preserved) ...
```

## Credits (Redis)

File: `docs/outputs/redis_credits.txt`

```
redis credits: None
```

## API Logs (Postgres)

File: `docs/outputs/api_logs.txt`

```
id | user_id | endpoint | credits_used |          created_at           
----+---------+----------+--------------+-------------------------------
 38 |       1 | /search  |            1 | 2025-11-27 01:17:08.544848+00
 37 |       1 | /person  |            1 | 2025-11-27 01:14:29.873779+00
 36 |       1 | /search  |            1 | 2025-11-27 01:14:29.754547+00
 35 |       1 | /search  |            1 | 2025-11-27 01:13:15.200341+00
 34 |       1 | /search  |            1 | 2025-11-27 01:10:45.631473+00
 33 |       1 | /search  |            1 | 2025-11-27 01:10:32.592015+00
 32 |       1 | /search  |            1 | 2025-11-27 01:09:23.316504+00
 31 |       1 | /search  |            1 | 2025-11-27 01:06:03.322917+00
 30 |       3 | /search  |            1 | 2025-11-27 00:40:36.051386+00
 29 |       3 | /search  |            1 | 2025-11-27 00:40:26.393545+00
(10 rows)

