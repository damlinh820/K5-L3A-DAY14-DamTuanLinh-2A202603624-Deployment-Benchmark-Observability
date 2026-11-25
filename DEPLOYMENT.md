# Deployment Information — Day 14

## Public URL

https://day14-production-agent-xw12.onrender.com

## Platform

Render web service. Repository deployment configuration is in `06-lab-complete/render.yaml`. The public service's commit and Blueprint association have not been independently verified.

## Environment variables

`ENVIRONMENT`, `AGENT_API_KEY`, `REDIS_URL`, `RATE_LIMIT_PER_MINUTE`, `DAILY_BUDGET_USD`. Secret values are intentionally omitted.

## Public HTTP checks

Observed on 2026-11-25 with JSON body `{"question":"Hello"}` for `POST /ask`:

| Request | Observed status | Expected | Result |
|---|---:|---:|---|
| `GET /health` | 200 | 200 | Pass |
| `GET /ready` | 200 (`{"status":"ready"}`) | 200 | Pass |
| `POST /ask` without `X-API-Key` | 401 | 401 | Pass |
| `POST /ask` with `X-API-Key` | Not run | 200 | Pending private key test |

The public service passes three of four HTTP checks. Part 3 remains pending until the authenticated request returns 200 and screenshots are saved.

## Recheck in WSL Bash

Set `BASE` to the public URL and enter the secret key without printing it:

```bash
BASE="https://day14-production-agent-xw12.onrender.com"
read -rsp "AGENT_API_KEY: " AGENT_API_KEY; echo
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'
```

Expected sequence: `200`, `200`, `401`, `200`. Do not paste the secret or the full authenticated command into a screenshot.

## Screenshots

- [x] [Deployment dashboard](screenshots/dashboard.png) (`screenshots/dashboard.png`)
- [x] [Service running](screenshots/running.png) (`screenshots/running.png`)
- [x] [Test results](screenshots/test.png) (`screenshots/test.png`)
