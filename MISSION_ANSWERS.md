# Day 14 Lab — Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1 — Anti-patterns

1. `01-localhost-vs-production/develop/app.py:17-18` hardcode API key giả và chuỗi kết nối DB có mật khẩu. Nếu thay bằng secret thật rồi đẩy lên Git, secret bị lộ.
2. `develop/app.py:34` in API key ra log; hệ thống thu thập log sẽ giữ bản sao secret.
3. `develop/app.py:20-21` bật `DEBUG=True` và đặt cấu hình trong mã, khó đổi giữa các môi trường.
4. `develop/app.py:48-54` cố định `localhost:8000` và `reload=True`; container không nhận kết nối từ bên ngoài, nền tảng cloud không thể cấp cổng qua `PORT`.
5. Bản develop không có `/health` hoặc `/ready`, nên bộ điều phối không có probe để xác định trạng thái.
6. Bản develop không có xử lý vòng đời hay dọn dẹp kết nối khi tắt.
7. `print()` thay cho logging có cấu trúc, khó truy vấn và đối chiếu request.

### Exercise 1.2 — Chạy bản develop

- Chạy bằng Python 3.11.9, FastAPI 0.115.0 và Uvicorn 0.30.0 trên Windows.
- `POST http://localhost:8000/ask?question=Hello` trả HTTP **200** và JSON có `answer` khi khởi chạy với `python -X utf8 app.py`.
- Lần chạy đầu không bật UTF-8 trả **500**: `UnicodeEncodeError` khi `print()` phản hồi có ký tự tiếng Việt vào console cp1252. Đây là lỗi phụ thuộc môi trường, không phải phản hồi thành công của ứng dụng.
- Endpoint develop nhận `question` qua **query parameter**; ví dụ gửi JSON trong hướng dẫn không khớp với chữ ký hàm hiện tại.

### Exercise 1.3 — So sánh

| Tính năng | Develop | Production mẫu | Vì sao cần |
|---|---|---|---|
| Cấu hình | Giá trị trong mã | `config.py` đọc biến môi trường | Đổi cấu hình mà không sửa mã/để lộ secret |
| Host và port | `localhost:8000` cố định | `HOST`, `PORT`, mặc định `0.0.0.0:8000` | Nhận traffic trong container/cloud |
| Health/readiness | Không có | `/health`, `/ready` trả 200 khi đã khởi động | Kiểm tra process và điều kiện nhận traffic |
| Logging | `print()`, gồm cả key | Logger, không in key | Truy vết an toàn hơn |
| Shutdown | Không có cleanup riêng | FastAPI lifespan có bước shutdown | Dọn dẹp tài nguyên khi dừng |

Kiểm chứng bản production mẫu: `GET /health` → **200**, `GET /ready` → **200** trên localhost. Chưa kiểm chứng request đang xử lý khi nhận SIGTERM. Bộ định dạng log mẫu chèn thông điệp JSON trực tiếp vào chuỗi JSON nên một số dòng có dấu nháy lồng nhau và **không phải JSON hợp lệ**; không coi mẫu này là structured logging hoàn chỉnh.

## Part 2: Docker

### Exercise 2.1 — Dockerfile cơ bản

1. Base image: `python:3.11` trong `02-docker/develop/Dockerfile`.
2. Working directory: `/app`.
3. Copy `requirements.txt` trước mã nguồn để lớp cài dependency có thể được tái sử dụng khi chỉ đổi mã nguồn.
4. `CMD` định nghĩa lệnh/đối số mặc định và có thể thay khi `docker run`; `ENTRYPOINT` định nghĩa chương trình chính, còn tham số khi `docker run` thường được nối vào chương trình đó.

### Exercise 2.2–2.3 — Build, chạy và đo image

Đo bằng `docker image inspect --format '{{.Size}}'` ngày 2026-11-25 trên Docker Desktop Linux engine:

| Cặp so sánh | Single-stage/develop | Multi-stage/production | Giảm |
|---|---:|---:|---:|
| Python agent | 1,667,788,367 byte (1.67 GB) | 239,815,376 byte (240 MB) | 85.63% |
| Go demo `02-docker/multi-stages/` | 1,306,554,163 byte (1.31 GB) | 22,608,814 byte (22.6 MB) | 98.27% |

Image Python develop: `/health` và `/ask?question=Docker` đều trả **200** trên cổng 18000. Image Python production: `/health`, `/ready` và `/ask` đều trả **200** trên cổng 18001. Image Go từ `Dockerfile-multistage`: `GET /` trả **200** trên cổng 18080; container đã dừng sau khi kiểm tra.

Trong `Dockerfile-multistage`, stage `builder` dùng `golang:1.22` để biên dịch binary tĩnh (`CGO_ENABLED=0`). Stage cuối dùng `alpine:3.19`, tạo `appuser`, chỉ copy `/app/myapp` từ builder; Go compiler và mã nguồn không nằm trong image cuối. Log build multi-stage hiển thị `CACHED` ở `WORKDIR`, `COPY` và `go build` sau khi build single-stage cùng context, chứng minh cache đã được dùng. Tuy nhiên `COPY . .` trước `go build` khiến sửa bất kỳ file nào trong context cũng có thể làm mất cache của bước biên dịch; ví dụ `02-docker/layer-order/Dockerfile.deps-first` tách `go.mod` và `main.go` để giữ cache dependency tốt hơn.

### Exercise 2.4 — Docker Compose

Stack `02-docker/production/docker-compose.yml` đã chạy với project `k5-day14-part2`: `nginx`, `agent`, `redis`, `qdrant` đều ở trạng thái running; `agent`, `redis`, `qdrant` healthy. `GET http://localhost/health` và `POST http://localhost/ask` qua Nginx đều trả **200**. Nginx nhận traffic cổng 80 rồi chuyển tới agent; agent và hai dịch vụ dữ liệu liên lạc qua network nội bộ `internal`, Redis/Qdrant không publish cổng ra host. Stack đã được dừng bằng `docker compose down` sau khi kiểm tra.

```text
Client → Nginx:80 → Agent:8000
                       ├─ Redis:6379 (session/cache)
                       └─ Qdrant:6333 (vector database)
```

Trong ví dụ hiện tại, agent chỉ được cấu hình URL Redis/Qdrant; mã `02-docker/production/main.py` chưa thực sự gọi hai dịch vụ đó trong `/ask`. Do vậy kiểm tra trên xác nhận stack khởi động và proxy hoạt động, chưa chứng minh tính năng session/RAG.

## Part 3: Cloud Deployment

### Exercise 3.1–3.2 — Railway và Render

**Đã chọn Render** cho Part 3. Blueprint mẫu tại `03-cloud-deployment/render/render.yaml` đã được chỉnh để chạy app minh họa từ `02-docker/production`, nhưng đó chưa phải bài deploy K5. Agent final trong `06-lab-complete/` hiện có `render.yaml` riêng: Docker build từ đúng thư mục con, `/health`, `AGENT_API_KEY` và `REDIS_URL` nhập qua Render Dashboard. Khi tạo Blueprint, trỏ tới `06-lab-complete/render.yaml` và cấu hình Redis trước khi kiểm `/ready`.

| Thuộc tính | Railway (cấu hình mẫu `03-cloud-deployment/railway/railway.toml`) | Render (Blueprint Part 3 `03-cloud-deployment/render/render.yaml`) |
|---|---|---|
| Định dạng | TOML, cấu hình build/deploy một service | YAML Blueprint, khai báo nhiều service |
| Build | `builder = "NIXPACKS"` | `runtime: python`, cài `02-docker/production/requirements.txt` |
| Start | `uvicorn app:app --host 0.0.0.0 --port $PORT` | `uvicorn main:app --app-dir 02-docker/production`, nghe `$PORT` |
| Health | `healthcheckPath = "/health"`, timeout 30 giây | `healthCheckPath: /health` |
| Restart/deploy | `ON_FAILURE`, tối đa 3 lần thử | `autoDeploy: true` khi push repo |
| Secret và Redis | Đặt biến môi trường qua dashboard/CLI; file mẫu chưa khai báo Redis | Agent mock Part 3 không dùng secret hay Redis, nên Blueprint chưa cấp hai tài nguyên này |

Blueprint đã sync commit `9c8d3c7` và tạo một service tại `https://day14-production-agent-jpuw.onrender.com`, nhưng service đó kết nối Redis lỗi (`/ready` → 503). URL public mới `https://day14-production-agent-xw12.onrender.com` đã được kiểm tra ngày 2026-11-25 và vượt qua đủ 4 phép thử CP6: `/health` → 200, `/ready` → 200, `/ask` không có key → 401, `/ask` có `X-API-Key` hợp lệ → 200 (`{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock)...","cost_usd":1.035e-05}`). Chi tiết ghi tại `DEPLOYMENT.md`; giá trị secret không lưu vào repo.

### Exercise 3.3 — Pipeline Cloud Run

`03-cloud-deployment/production-cloud-run/cloudbuild.yaml` mô tả chuỗi `test → build Docker image → push lên registry → deploy Cloud Run`. Build gắn tag theo commit SHA và `latest`, đồng thời yêu cầu cache từ image `latest`. Bước deploy đặt region `asia-southeast1`, min/max instance, CPU/RAM, timeout và nạp secret qua Secret Manager. `service.yaml` mô tả container port 8000, concurrency 80, `/health` làm liveness probe và `/ready` làm startup probe. Đây là mô tả pipeline mẫu; repo chưa có lần chạy Cloud Build hay Cloud Run được xác minh. Bước `pytest tests/` trong YAML cũng cần một thư mục `tests/` phù hợp trước khi chạy thực tế.

## Part 4: API Security

### Exercise 4.1 — API key

Trong `04-api-gateway/develop/app.py`, `verify_api_key()` đọc header `X-API-Key` qua `APIKeyHeader`; thiếu key trả **401**, key sai trả **403**, key đúng cho phép `/ask` trả **200**. Chạy localhost đã xác nhận thiếu key → 401 và key demo đúng → 200. Key đọc từ `AGENT_API_KEY` khi process khởi động; muốn rotate cần đổi biến môi trường và restart/redeploy (mẫu chỉ hỗ trợ một key tại một thời điểm). Mẫu có fallback key demo và in key khi khởi động, không dùng nguyên trạng cho production.

### Exercise 4.2–4.3 — JWT và rate limit

Trong `04-api-gateway/production/auth.py`, `POST /auth/token` xác thực demo user rồi ký JWT HS256 gồm `sub`, `role`, `iat`, `exp` (60 phút). `/ask` yêu cầu Bearer token. Đây là endpoint thật trong code; ví dụ `/token` trong `CODE_LAB.md` không khớp. Bài thử localhost: thiếu token → **401**; JWT hợp lệ của user demo → **200**. `RateLimiter` dùng sliding window in-memory theo username: user tối đa 10 request/60 giây; admin tối đa 100. Request thứ 10 → **200**, thứ 11 → **429**, có `Retry-After` (quan sát 48 giây trong lần kiểm tra tiếp). Bằng chứng và lệnh tái hiện: `evidence/part4-http.md`.

### Exercise 4.4 — Cost guard

`04-api-gateway/production/cost_guard.py` tính chi phí từ input/output token, kiểm tra budget trước khi gọi LLM và ghi nhận usage sau đó. Kiểm thử trực tiếp một `CostGuard(daily_budget_usd=0.000001)` sau khi ghi 1.000 input + 1.000 output token đã ném HTTP **402**, với `used_usd=0.00075`. Mẫu hiện dùng RAM, budget **$1/ngày/user** và **$10/ngày tổng**, chưa đáp ứng bài tập mở rộng **$10/tháng/user lưu Redis**. Muốn đáp ứng khi scale cần key Redis theo user + tháng, thao tác kiểm tra/cộng chi phí nguyên tử và TTL tới đầu tháng sau; không thể coi mẫu RAM là guard dùng chung nhiều instance.

Lưu ý bảo mật: `04-api-gateway/production/auth.py` còn fallback `JWT_SECRET` cố định và tài khoản demo hardcode; phải bỏ trước khi dùng production. Invalid JWT hiện trả **403**, còn thiếu token trả **401**.

## Part 5: Scaling & Reliability

### Exercise 5.1 — Health và readiness

Stack `05-scaling-reliability/production/` chạy với 3 agent, Redis và Nginx. Khi Redis hoạt động, `/health` trả **200** với `storage=redis`, `redis_connected=true`; `/ready` trả **200**. Khi dừng Redis, `/health` vẫn trả **200** với `status=degraded`, `redis_connected=false`, còn `/ready` của agent trả **503**. Qua Nginx, `/ready` trả **502** do cấu hình `proxy_next_upstream http_503` thử lại các upstream rồi báo lỗi gateway. Sau khi khởi động lại Redis, `/ready` qua Nginx trở lại **200**. Liveness cho biết process còn sống; readiness cho biết đã có dependency cần thiết để nhận traffic.

### Exercise 5.2 — Graceful shutdown

Đã dừng một agent bằng `docker stop k5-day14-scaling-agent-2`: container thoát với exit code **0**; log có `Shutting down`, `Instance ... shutting down`, `Application shutdown complete`. Đây là bằng chứng shutdown sạch khi không có request đang xử lý; chưa chứng minh một request đang chạy hoàn tất trong lúc nhận SIGTERM. Mã production dùng FastAPI lifespan để log cleanup, còn Uvicorn xử lý SIGTERM.

### Exercise 5.3–5.5 — Redis, nhiều instance và state chung

`docker compose -p k5-day14-scaling up -d --build --scale agent=3` khởi động ba agent, Redis và Nginx. `test_stateless.py` gửi 5 lượt chat cùng session: các response được phục vụ bởi **3 instance khác nhau**, lịch sử có **10 message** (5 user + 5 assistant). Sau khi dừng agent số 2, request tiếp theo được instance khác xử lý, `storage=redis` và lịch sử tăng lên **12 message**. Điều này xác nhận session được chia sẻ qua Redis trong phép thử. Script `test_stateless.py` tự nó không dừng instance hay assert kết quả; bước dừng agent và kiểm tra lại được thực hiện riêng. Kết quả chi tiết ở `evidence/part5-scaling.md`.

Giới hạn: `05-scaling-reliability/production/app.py` fallback sang dictionary trong RAM nếu Redis không kết nối được lúc khởi động, khi đó thiết kế không còn stateless. Nên fail readiness thay vì phục vụ session in-memory trong triển khai nhiều instance.

## Part 6: Final Project

Hoàn thiện các `TODO` trực tiếp trong `06-lab-complete/`. Bộ chấm `python check_production_ready.py` đã được chạy đầy đủ với Docker 29.9.3 (không sửa `check_production_ready.py`), đạt **`PASS 12/12` (43/43 checks passed)**:

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

Chi tiết kiểm chứng từ output script chấm:
- Docker image multi-stage (`python:3.11-slim`, user non-root `agent`, có `HEALTHCHECK`): kích thước **274 MB** (< 500 MB).
- `GET /health` → **200**; `GET /ready` → **200** (khi dừng Redis thì `/ready` → **503** trong khi `/health` vẫn **200**).
- `X-API-Key` thiếu hoặc sai → **401**; key đúng → **200**.
- Rate limit (sliding window bằng Redis Lua script): **429** sau 5 request thành công (`RATE_LIMIT_PER_MINUTE=5`), và vẫn giữ **429** sau khi restart agent.
- Cost guard (lưu chi phí micro-USD trong Redis): **402** khi vượt `DAILY_BUDGET_USD`.
- Graceful shutdown: nhận `SIGTERM` khi đang xử lý request thì request đó vẫn trả **200** và process tự thoát với exit code **0**; `docker stop` thoát với exit code **0** trong **0.8s** (< 10s).
- Structured logging: mọi dòng log của ứng dụng là JSON hợp lệ (**12 dòng JSON**).

## AI log

- 2026-11-25 — Hỏi AI đọc README, checkpoint và rubric để tóm tắt công việc. AI chỉ ra Part 1–5 là phần chạy mẫu và giải thích, Part 6 là agent production, Part 7 là benchmark/observability. Đối chiếu lại với `README.md`, `CHECKPOINTS.md`, `RUBRIC.md` và `RULES.md`.
- 2026-11-25 — Nhờ AI hoàn tất Part 1–5, rà `RULES.md` và triển khai Part 6. AI viết các module trong `06-lab-complete/app/`, Dockerfile, Compose, `.dockerignore`, `.env.example`, config Railway/Render; cập nhật phần báo cáo này. Kiểm tra bằng `check_production_ready.py --static-only` (28/28 kiểm tra tĩnh) và bộ chấm đầy đủ (43/43, `PASS 12/12`) trên Linux/Python 3.11.
- 2026-11-25 — Hỏi AI cách tự deploy Part 3 trên Render. AI đối chiếu tài liệu Render và sửa `dockerfilePath`/`dockerContext` trong `06-lab-complete/render.yaml` cho đúng đường dẫn tính từ gốc repo, chọn gói Free ở Singapore, để Render hỏi `AGENT_API_KEY` và `REDIS_URL` lúc tạo Blueprint.
- 2026-11-25 — Nhờ AI kiểm URL Render sau khi tạo Blueprint. AI gọi ba endpoint public: `/health` 200, `/ready` 503, `/ask` không key 401; tạo `DEPLOYMENT.md` ghi rõ phép thử có key chưa chạy.
- 2026-11-25 — Sau khi đổi Redis và nhận URL Render mới, nhờ AI kiểm lại endpoint. AI quan sát `/health` 200, `/ready` 200, `/ask` không key 401 và cập nhật báo cáo.
- 2026-11-25 — Nhờ AI hướng dẫn và thực hiện Part 7 (CP7 & CP8) và kiểm tra lại Part 6 theo đúng `SUBMISSION.md`, `RUBRIC.md`, `RULES.md`:
  - **Hỏi gì:** Cách thêm metric `agent_question_length_chars` (Exercise 7.1), chạy load test 4 mức concurrency và 3 mức `MOCK_SLOW_RATE` (Exercise 7.2), sửa `KNOWLEDGE_BASE` cho 2 câu `security-02` và `scaling-03` cùng cấu hình CI quality gate (Exercise 7.3), sửa lỗi `PYTHONUSERBASE` trong `06-lab-complete/benchmark-observability/production/Dockerfile` khi chạy user non-root `agent`, và chạy stack Observability (Prometheus, Grafana, Jaeger, Locust) để đo scaling 1 vs 3 instance và test 4 alert rules (Exercise 7.4–7.7).
  - **Nhận gì:** AI gợi ý dùng `Histogram` cho `agent_question_length_chars`, bổ sung 2 mục từ khóa `["jwt"]` và `["hpa", "kubernetes", "autoscal"]` vào `KNOWLEDGE_BASE` trong `utils/mock_llm.py` (không sửa `golden_dataset.jsonl` hay `check_production_ready.py`), thêm `ENV PYTHONUSERBASE=/home/agent/.local` vào Dockerfile của Part 7 production, và hướng dẫn lệnh chạy `load_test.py`, `run_eval.py`, `promtool test rules`, và Locust headless.
  - **Tự sửa và tự kiểm tra thế nào:** Chạy lại `check_production_ready.py` xác nhận `PASS 12/12` (43/43 checks); chạy `run_eval.py --min-accuracy 1.0 --baseline reports/eval_v2.json --out reports/eval_v2_fixed.json` đạt 23/23 câu đúng (100%, 0 regression, `Quality gate: ✅ PASS`); kiểm tra `promtool test rules` báo `SUCCESS`; đối chiếu toàn bộ số liệu trong `BENCHMARK_REPORT.md` khớp 100% với 10 file JSON trong `reports/` và 2 file CSV (`scale_1_stats.csv`, `scale_3_stats.csv`) trong `benchmark-results/`; chụp đủ 7 ảnh trong `screenshots/` và tắt stack Docker bằng `docker compose -p k5-day14-observability down -v`.
