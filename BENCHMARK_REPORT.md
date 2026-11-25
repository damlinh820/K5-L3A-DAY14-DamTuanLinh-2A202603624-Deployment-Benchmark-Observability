# Benchmark & Observability Report — Day 14

> Copy file này thành `BENCHMARK_REPORT.md` trong repo của bạn và điền đầy đủ.
> Mọi con số phải lấy từ report JSON / CSV / screenshot thật, không ước lượng.

**Họ tên:** DamTuanLinh - 2A202603624
**Ngày chạy:** 2026-11-25
**Môi trường:** Windows 11 + WSL2 Ubuntu, Python 3.11.9, Docker Desktop 29.9.3 (Linux containers)

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | ≤ 500 ms | Đảm bảo 95% request của người dùng nhận phản hồi trong nửa giây (ngưỡng mặc định của `load_test.py --slo-p95-ms 500`), phù hợp với baseline latency LLM ~150–250 ms cộng bước retrieval ~20 ms mà không bị đánh lừa bởi latency trung bình. |
| Error rate `/ask` | ≤ 2.0 % | Cho phép error budget 2% để hấp thụ lỗi thoáng qua (~1% `MOCK_ERROR_RATE` mặc định từ upstream LLM 503) mà vẫn bảo vệ trải nghiệm người dùng; ngưỡng alert đặt lỏng hơn ở 5% trong 1 phút để tránh alert fatigue. |
| Accuracy trên golden dataset | ≥ 85 % (CI gate) / 100 % (sau khi sửa KB) | Chặn các bản release có chất lượng thấp như v1 (4.35%) hoặc bị regression khi thay đổi prompt/retrieval; sau khi bổ sung tài liệu còn thiếu vào `KNOWLEDGE_BASE`, yêu cầu đạt 100% (23/23 câu đúng) và 0 regression. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

Kết quả trích xuất trực tiếp từ `reports/load_v2_c1.json`, `reports/load_v2_c10.json`, `reports/load_v2_c50.json`, `reports/load_v2_c100.json` (300 requests mỗi mức):

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---:|---:|---:|---:|---:|---|
| 1 | 4.02 | 202.6 | 234.5 | 1715.2 | 1.00% (0.01) | PASS |
| 10 | 34.11 | 194.7 | 443.3 | 1703.0 | 0.67% (0.0067) | PASS |
| 50 | 78.22 | 229.9 | 1087.2 | 1997.0 | 0.67% (0.0067) | FAIL (p95 > 500ms) |
| 100 | 45.34 | 748.8 | 4094.3 | 4741.0 | 2.00% (0.02) | FAIL (p95 > 500ms) |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

- Từ `concurrency=1` lên `10`, RPS tăng gần tuyến tính từ **4.02 req/s** lên **34.11 req/s** (~8.5 lần) vì event loop `asyncio` của Uvicorn tận dụng thời gian chờ I/O (`asyncio.sleep` ở bước retrieval và gọi LLM) để xử lý xen kẽ các request khác; p50 giữ ổn định quanh ~195–203 ms và p95 đạt 443.3 ms (vẫn đạt SLO ≤ 500 ms).
- Từ `concurrency=10` lên `50`, RPS chỉ tăng thêm ~2.3 lần (đạt **78.22 req/s**) trong khi p95 tăng vọt lên **1087.2 ms** (vi phạm SLO). Khi tiếp tục tăng lên `concurrency=100`, thông lượng suy giảm còn **45.34 req/s**, p50 tăng lên **748.8 ms** và p95 vọt lên **4094.3 ms**.
- **Nguyên nhân:** Một tiến trình Uvicorn đơn lẻ trên máy local chịu chi phí chuyển ngữ cảnh (context switching), tranh chấp socket/event loop và xếp hàng (queuing delay theo định luật Little $L = \lambda W$) khi 50–100 kết nối đồng thời cùng gửi và đọc JSON cũng như ghi log đồng bộ ra stdout. Do đó RPS không thể tăng tuyến tính mãi theo concurrency mà đạt đỉnh rồi suy giảm khi hệ thống bão hòa.

### 2.2 Tail latency

Kết quả trích xuất từ `reports/load_v2_slow_0.json`, `reports/load_v2_slow_0.03.json`, `reports/load_v2_slow_0.1.json` (`--requests 300 --concurrency 20`):

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) | RPS | Error rate | SLO |
|---|---:|---:|---:|---:|---:|---|
| 0 | 208.9 | 436.1 | 498.3 | 92.39 | 1.00% (0.01) | PASS |
| 0.03 (mặc định) | 252.4 | 495.4 | 1696.4 | 61.27 | 1.33% (0.0133) | PASS |
| 0.1 | 325.9 | 1682.5 | 1713.4 | 50.63 | 1.67% (0.0167) | FAIL |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

- **Chỉ số nhạy nhất:** Khi `MOCK_SLOW_RATE` tăng từ `0` lên `0.03` (chỉ 3% request bị cộng thêm 1500 ms), `avg` chỉ tăng nhẹ từ **208.9 ms** lên **252.4 ms** (+43.5 ms) và `p95` vẫn ở mức **495.4 ms**, nhưng **`p99` nhảy vọt từ 498.3 ms lên 1696.4 ms** (tăng hơn 3.4 lần). Khi `MOCK_SLOW_RATE` tăng lên `0.1` (10% request chậm, vượt ngưỡng 5% của đuôi phân phối), cả **`p95` cũng nhảy vọt lên 1682.5 ms** (cùng `p99` ở **1713.4 ms**), trong khi `avg` mới chỉ là **325.9 ms**.
- **Vì sao không đặt SLO theo average:** Giá trị trung bình cộng (`avg`) san phẳng các giá trị ngoại lai (outliers) vào đa số request nhanh, khiến `avg = 252.4 ms` hoặc `325.9 ms` trông vẫn rất tốt (< 500 ms) dù thực tế có 3% đến 10% người dùng phải chờ ~1.7 giây. Đặt SLO theo percentile (`p95`, `p99`) giúp đo trực tiếp trải nghiệm của nhóm người dùng ở phần đuôi phân phối (tail latency) và phát hiện sớm hiện tượng nghẽn cổ chai.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Kết quả trích xuất trực tiếp từ `reports/eval_v1.json`, `reports/eval_v2.json` và `reports/eval_v2_fixed.json` (trên 23 câu hỏi trong `golden_dataset.jsonl`):

| Chỉ số | Agent v1 (`eval_v1.json`) | Agent v2 (`eval_v2.json`) | Agent v2 sau khi sửa KB (`eval_v2_fixed.json`) |
|---|---:|---:|---:|
| Accuracy | 4.35% (0.0435 — 1/23) | 91.30% (0.913 — 21/23) | 100.00% (1.0 — 23/23) |
| Avg tokens / câu | 57.2 | 109.0 | 113.7 |
| Tổng cost (USD) | $0.000406 | $0.000760 | $0.000790 |
| Cost / câu đúng (USD) | $0.00040575 | $0.00003619 ($3.619e-05) | $0.00003436 ($3.436e-05) |
| Latency p50 / p95 (ms) | 184.2 / 1497.6 | 201.9 / 234.1 | 201.2 / 245.2 |
| Quality gate | FAIL (min 80%) | PASS (min 80%, 0 regression) | PASS (min 100%, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm mục từ khóa `["jwt"]` vào `KNOWLEDGE_BASE` trong `utils/mock_llm.py`: *"API key là chuỗi bí mật cố định, không tự hết hạn. JWT là token có chữ ký số, chứa thông tin user và thời điểm hết hạn; server xác minh chữ ký mà không cần tra database."* |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm mục từ khóa `["hpa", "kubernetes", "autoscal"]` vào `KNOWLEDGE_BASE` trong `utils/mock_llm.py`: *"Kubernetes HPA (Horizontal Pod Autoscaler) scale số pod dựa trên CPU, memory hoặc custom metrics như RPS hay độ dài hàng đợi."* |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

- **Token & Chi phí:** Agent v2 bổ sung tài liệu từ bước retrieval (RAG) vào prompt nên số token trung bình mỗi câu tăng gấp ~2 lần (từ **57.2** lên **109.0** và **113.7** token/câu), làm tổng chi phí cho 23 câu tăng từ **$0.000406** lên **$0.000760** (và **$0.000790** sau khi sửa KB). Tuy nhiên, vì v1 hầu như trả lời sai (chỉ đúng 1/23 câu = 4.35%), **chi phí trên mỗi câu trả lời đúng (`cost_per_correct_usd`) của v2 rẻ hơn hơn 11 lần**: giảm từ **$0.00040575/câu đúng** (v1) xuống còn **$0.00003619/câu đúng** (v2 ban đầu) và **$0.00003436/câu đúng** (v2 sau khi sửa KB).
- **Latency:** Bước retrieval tăng thêm ~20 ms (`p50` của v2 là **201.2–201.9 ms** so với **184.2 ms** của v1). Đánh đổi ~17–20 ms latency và gấp đôi số token để tăng độ chính xác từ 4.35% lên 100% là hoàn toàn xứng đáng.
- **Quality gate trong CI/CD (Exercise 7.3):** Script `eval/run_eval.py` kết thúc bằng `raise SystemExit(0 if gate_ok else 1)`, trong đó `gate_ok = (accuracy >= min_accuracy) and (len(regressions) == 0)`. Khi chạy `run_eval.py` cho v1 với `--baseline reports/eval_v2.json` hoặc khi v2 có bất kỳ câu nào đang đúng ở baseline bị tụt điểm (regression) hoặc tổng accuracy thấp hơn ngưỡng `--min-accuracy`, script trả về **exit code `1`**. Trong GitHub Actions (đã cấu hình tại `.github/workflows/eval.yml`), step chạy `python eval/run_eval.py --url http://localhost:8000 --min-accuracy 0.85` nhận exit code khác 0 sẽ đánh dấu workflow `FAIL`, từ đó chặn merge Pull Request (branch protection rule).

---

## 4. Observability stack (production)

### 4.1 Screenshot và trả lời câu hỏi Exercise 7.1 & 7.4

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals): `screenshots/grafana-dashboard.png`
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian): `screenshots/jaeger-slow-trace.png`
- [x] Một trace lỗi trong Jaeger (có event `exception`): `screenshots/jaeger-error-trace.png`
- [x] Trang Alerts của Prometheus với ít nhất 2 alert đang **firing** (có 3 alert cùng firing): `screenshots/prometheus-alert-firing.png`

**Trả lời câu hỏi Exercise 7.1 (Metrics trong `develop/app.py`):**
1. **Ví dụ 3 loại metric trong `/metrics`:**
   - **Counter** (chỉ tăng, dùng với `rate()`): `http_requests_total{method="POST",route="/ask",status="200"}`, `llm_tokens_total{model="mock-llm-small",type="input"}`, `llm_cost_usd_total{model="mock-llm-small"}`.
   - **Gauge** (có thể tăng/giảm): `agent_in_flight_requests`, `agent_info{model="mock-llm-small",version="v2"} 1.0`.
   - **Histogram** (chia vào các bucket `_bucket{le="..."}`, kèm `_sum` và `_count`): `http_request_duration_seconds_bucket`, `llm_request_duration_seconds_bucket`, và metric mới thêm `agent_question_length_chars_bucket`.
2. **Vì sao dùng `route.path` (template) thay vì `request.url.path`:** Nếu gắn URL thật vào label `route`, khi bot quét hàng nghìn đường dẫn ngẫu nhiên (`/wp-admin`, `/.env`, `/user/12345`...), mỗi URL duy nhất sẽ tạo ra một tổ hợp label mới (1 time series mới). Hiện tượng **cardinality explosion** này làm Prometheus tiêu tốn hết RAM và làm chậm truy vấn. Khi dùng `route.path` (và gom mọi đường dẫn không khớp về `"unmatched"`), số lượng giá trị của label `route` luôn cố định ở vài endpoint đã định nghĩa.

**Trả lời câu hỏi Exercise 7.4 (Đọc Dashboard Grafana dưới tải 30 users):**
1. **p95 và avg đang là bao nhiêu? Khoảng cách giữa chúng nói lên điều gì?**
   - Khi chạy tải 30 users, Prometheus/Grafana ghi nhận `avg` khoảng **218.7 ms**, `p95` khoảng **288.1–290.8 ms**, còn `p99` trên biểu đồ *Latency /ask — p50 / p95 / p99* vọt lên mức **~1.70–1.75 s**.
   - Khoảng cách lớn giữa đường trung bình (`avg ~219 ms`) và các đường phân vị cao (`p95 ~288 ms`, `p99 ~1.7 s`) phản ánh hiện tượng **tail latency**: đa số request hoàn tất quanh 190–220 ms, nhưng ~3% request rơi vào nhánh `MOCK_SLOW_RATE` (tốn ~1.7 s) bị trung bình cộng che khuất.
2. **Panel "Requests/s theo instance": Nginx có chia đều traffic cho các instance không?**
   - **Có.** Nginx sử dụng cơ chế round-robin với `server agent:8000 resolve;` qua Docker DNS. Trên panel *Requests/s theo instance* (và khi truy vấn trực tiếp `sum by (instance) (rate(http_requests_total{route="/ask"}[1m]))`), lưu lượng được chia đều cho cả 3 instance: `172.18.0.4:8000` đạt **2.44 req/s**, `172.18.0.6:8000` đạt **2.29 req/s**, và `172.18.0.9:8000` đạt **2.24 req/s** (khi chạy tải tối đa 100 users, mỗi instance nhận đều ~20 req/s, tổng ~60.5 req/s).
3. **Vì sao input tokens/s lớn hơn output tokens/s?**
   - Trên panel *Tokens/s*, `input` đạt **~531.8 tokens/s** (đỉnh ~7.3K tokens/s khi chạy 100 users) trong khi `output` chỉ đạt **~277.6 tokens/s** (đỉnh ~4.8K tokens/s). Lý do là ở `AGENT_VERSION=v2`, mỗi lần gọi LLM đều ghép `SYSTEM_PROMPT` + đoạn tài liệu `context` lấy từ bước retrieval (RAG) + `question` của người dùng vào phần input (~80–100 input tokens), trong khi câu trả lời trả về ngắn gọn (~40–55 output tokens).
4. **`curl http://localhost:8080/metrics` trả về gì? Vì sao?**
   - Lệnh trả về **`HTTP/1.1 404 Not Found`** từ `nginx/1.28.3`.
   - Lý do: Trong `nginx/nginx.conf`, khối `location = /metrics { return 404; }` chủ động chặn truy cập `/metrics` từ cổng public bên ngoài vì endpoint này tiết lộ thông tin nhạy cảm về nội bộ hệ thống (cấu trúc route, lưu lượng traffic, tỷ lệ lỗi, phiên bản model, chi phí). Prometheus nằm trong cùng mạng nội bộ `obs_net` nên scrape trực tiếp `agent:8000/metrics` qua Docker DNS mà không đi qua Nginx.

### 4.2 Thí nghiệm "phá hệ thống"

Unit test cho bộ quy tắc cảnh báo bằng `promtool test rules /p/alert_rules_test.yml` đạt kết quả **`SUCCESS`**. Kết quả thực nghiệm trên stack Docker Compose:

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`severity="critical"`, ngưỡng > 5%, `for: 1m`) | **86.9 giây** (~1 phút 27 giây: ~25s để cửa sổ `rate(...[1m])` vượt 5% và chuyển sang `pending`, cộng 60s `for: 1m`) | Panel **Error rate** (Golden Signals, chuyển sang màu đỏ ~17.5–17.6%), **Requests/s theo status code** (đường `503` tăng vọt) và **LLM calls theo kết quả** (`error`). |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`severity="warning"`, ngưỡng > 1s, `for: 2m`) | **143.0 giây** (~2 phút 23 giây: ~23s để `p95` vượt 1s lên ~1.94–1.97s và vào `pending`, cộng 120s `for: 2m`) | Panel **Latency p95** (Golden Signals, đỏ ở ~1.94s), **Latency /ask — p50 / p95 / p99** và **LLM latency p95 theo model**. |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (`severity="warning"`, ngưỡng > \$2/giờ, `for: 2m`) | **162.8 giây** (~2 phút 43 giây: ~43s để tốc độ chi tiêu trên cửa sổ `rate(...[5m]) * 3600` vượt \$2/giờ lên ~\$13.49/giờ và vào `pending`, cộng 120s `for: 2m`) | Panel **Cost burn rate (USD/giờ)** (vượt vạch đỏ \$2/giờ lên ~\$13.5/giờ), **LLM cost (1h)** và bảng **Phiên bản đang chạy** (hiện model `mock-llm-large`). |
| D | `docker pause` 1 instance (`k5-day14-observability-agent-1`) | `AgentInstanceDown` (`severity="critical"`, `up{job="agent"} == 0`, `for: 30s`) | **40.1 giây** (~10s để Prometheus scrape timeout và đánh dấu `up == 0` → `pending`, cộng 30s `for: 30s`) | Panel **Instances up** (giảm từ 3 xuống 2) và **Requests/s theo instance** (1 instance rơi về 0 req/s). |
| E | `AGENT_VERSION=v1` | **Không có alert nào firing** | Không firing (0 alert) | Panel **Retrieval hit ratio (agent v2)** (mất dữ liệu vì v1 không gọi retrieval), **Tokens/s** (input token giảm mạnh) và bảng **Phiên bản đang chạy** (`version="v1"`). |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào? (kèm giải thích hiện tượng ở Thí nghiệm D):**

- **Phát hiện sự cố suy giảm chất lượng ở Thí nghiệm E:** Khi chuyển sang `AGENT_VERSION=v1`, ứng dụng vẫn trả HTTP `200 OK` nhanh hơn và tốn ít token hơn nên mọi chỉ số hạ tầng (Traffic, Error rate, Latency p95, Saturation, Cost) đều "xanh". Để bắt loại lỗi chất lượng (silent quality degradation) này trong production cần kết hợp 3 lớp:
  1. **Trước khi deploy (CI/CD Quality Gate):** Chạy `eval/run_eval.py` trên golden dataset với `--min-accuracy` và `--baseline` để chặn ngay bản build có accuracy tụt từ 100% xuống 4.35%.
  2. **Giám sát chỉ số nghiệp vụ / hành vi pipeline (Domain Metrics):** Đặt alert khi chỉ số `rate(agent_retrieval_total[5m]) == 0` (pipeline RAG ngừng truy xuất tài liệu) hoặc khi tỷ lệ người dùng bấm dislike / yêu cầu hỏi lại tăng đột biến.
  3. **Online Eval / LLM-as-a-Judge:** Lấy mẫu (sampling 1–5%) log hội thoại thực tế trên production để chấm điểm tự động bằng model giám khảo (LLM-as-a-judge) và đẩy metric điểm chất lượng về Prometheus.
- **Giải thích Thí nghiệm D (`docker pause` và lỗi 504 ở Nginx):**
  - Dùng `docker pause` thay vì `docker stop` vì Prometheus khám phá target qua Docker DNS (`dns_sd_configs`). Nếu `stop`, container bị gỡ khỏi DNS nên Prometheus không còn thấy target đó nữa; ngược lại khi `pause`, IP vẫn còn trong DNS nhưng không phản hồi scrape `/metrics`, giúp `up{job="agent"} == 0` kích hoạt `AgentInstanceDown`.
  - Lỗi `504 Gateway Timeout` khi Nginx chờ instance bị treo quá `proxy_read_timeout` do **Nginx tự sinh ra và trả về cho client**, trong khi request đó chưa bao giờ được tiến trình FastAPI của agent xử lý xong để ghi nhận vào middleware `observe_requests`. Vì vậy `http_requests_total` của agent không đếm các lỗi 504 này. Trong production, cần thu thập thêm metrics tại tầng Load Balancer / API Gateway (Nginx exporter) hoặc chạy synthetic blackbox probing từ bên ngoài hệ thống.

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất tìm được trong Jaeger (`screenshots/jaeger-slow-trace.png`):

- `trace_id`: `637c689086ff0d0d6a1aa7eb0fb5ab0b`
- Tổng thời gian (`POST /ask`): **1724.45 ms** (log middleware ghi `1723.4 ms`)
- Các span con bên trong:
  - `agent.run`: **1721.64 ms** (99.84%)
  - `agent.retrieve_context`: **22.40 ms** (1.30%)
  - Span chiếm nhiều thời gian nhất: **`chat mock-llm-small`** (**1699.06 ms**, chiếm **98.53%** tổng thời gian request) → Chứng minh độ trễ nằm ở bước gọi upstream LLM chứ không phải ở code FastAPI hay bước tìm kiếm tài liệu retrieval.
- Dòng log JSON tương ứng (grep theo `trace_id` `637c689086ff0d0d6a1aa7eb0fb5ab0b` từ `docker compose -p k5-day14-observability logs agent`):

```json
{"ts": "2026-11-25T12:59:08.919031+00:00", "level": "INFO", "service": "observable-agent", "instance": "3956f4c84022", "event": "llm_call", "trace_id": "637c689086ff0d0d6a1aa7eb0fb5ab0b", "span_id": "64a7d2ef251a135e", "request_id": "06c763550d1d", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1699.0}
{"ts": "2026-11-25T12:59:08.919391+00:00", "level": "INFO", "service": "observable-agent", "instance": "3956f4c84022", "event": "http_request", "trace_id": "637c689086ff0d0d6a1aa7eb0fb5ab0b", "span_id": "64a7d2ef251a135e", "request_id": "06c763550d1d", "method": "POST", "route": "/ask", "status": 200, "ms": 1723.4}
```

Trace lỗi (`screenshots/jaeger-error-trace.png`) đối chiếu:
- `trace_id`: `6a191876dc054991ead248ce9002afbd` (tổng thời gian **107.29 ms**, trong đó `agent.retrieve_context` = **19.26 ms**, `chat mock-llm-small` = **86.48 ms** có gắn tag `error.type = upstream_unavailable` và event `exception`: `Upstream LLM error: 503 Service Unavailable (mock)`).
- Dòng log JSON tương ứng khi chạy `docker compose -p k5-day14-observability logs agent | grep llm_error`:

```json
{"ts": "2026-11-25T13:00:24.111360+00:00", "level": "INFO", "service": "observable-agent", "instance": "3956f4c84022", "event": "llm_error", "trace_id": "6a191876dc054991ead248ce9002afbd", "span_id": "dd35fcdde6027db1", "request_id": "f485b522954e", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
{"ts": "2026-11-25T13:00:24.111600+00:00", "level": "INFO", "service": "observable-agent", "instance": "3956f4c84022", "event": "http_request", "trace_id": "6a191876dc054991ead248ce9002afbd", "span_id": "dd35fcdde6027db1", "request_id": "f485b522954e", "method": "POST", "route": "/ask", "status": 503, "ms": 106.9}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu trích xuất chính xác từ `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv` (bao gồm cả dòng riêng cho `POST /ask` và dòng `Aggregated` tổng hợp cả `/ask` và `/health`):

| Số instance | Dòng thống kê (CSV) | Request Count | RPS (`Requests/s`) | avg (ms) | p50 (ms) | p95 (ms) | p99 (ms) | Failures (`Failure Count`) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **1** (`scale_1_stats.csv`) | `POST /ask` | 7202 | **60.21** (60.2060) | 230.76 | **190** | **220** | **1700** | **66** (0.92%, 0.55 fails/s) |
| **1** (`scale_1_stats.csv`) | `Aggregated` | 7916 | **66.17** (66.1748) | 210.25 | **190** | **220** | **1700** | **66** (0.83%, 0.55 fails/s) |
| **3** (`scale_3_stats.csv`) | `POST /ask` | 7233 | **60.49** (60.4876) | 237.25 | **190** | **220** | **1700** | **91** (1.26%, 0.76 fails/s) |
| **3** (`scale_3_stats.csv`) | `Aggregated` | 7915 | **66.19** (66.1910) | 217.09 | **190** | **220** | **1700** | **91** (1.15%, 0.76 fails/s) |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

- **Scale từ 1 lên 3 instance giữ nguyên `p50 = 190 ms`, `p95 = 220 ms`, `p99 = 1700 ms` và tổng thông lượng `RPS ≈ 66.2 req/s` (`POST /ask ≈ 60.2–60.5 req/s`).**
- **Vì sao thông lượng và p95 không tăng thêm?**
  1. **Nút thắt về Latency nằm ở bước gọi Upstream LLM (I/O-bound):** Như đã thấy trên panel *LLM latency p95 theo model* của Grafana và trace trong Jaeger, 98.5% thời gian xử lý mỗi request nằm ở bước chờ phản hồi từ LLM (`await asyncio.sleep(...)` ~140–200 ms, cộng 3% tail latency ~1700 ms) và ~20 ms chờ retrieval. Vì ứng dụng viết bằng `async/await` trên FastAPI/Uvicorn, bản thân container không bị nghẽn CPU ở mức 60 req/s (~15–20 request in-flight đồng thời).
  2. **Giới hạn tốc độ phát tải của 100 Locust users (Pacing / Wait Time):** Trong `locustfile.py`, mỗi user có `wait_time = between(0.5, 2)` (trung bình nghỉ **1.25 giây** giữa hai request) cộng thời gian xử lý trung bình **~0.21 giây** → chu kỳ mỗi user là $1.25 + 0.21 = 1.46\text{ giây}$. Theo định luật Little, với $N = 100\text{ users}$, thông lượng tối đa mà client sinh ra được là $\lambda = 100 / 1.46 \approx 68.5\text{ req/s}$ (và do mất 10 giây đầu ramp-up với `-r 10`, thông lượng trung bình trong 120 giây hội tụ đúng ở mức **~66.2 req/s**).
  3. **Lợi ích thực sự của việc scale lên 3 instance:** Tải CPU/RAM và số request in-flight được chia đều cho 3 container (~20 req/s mỗi instance thay vì dồn hết lên 1 instance), đồng thời đảm bảo tính sẵn sàng cao (High Availability): khi 1 instance gặp sự cố hoặc bị restart, Nginx tự động chuyển tiếp lưu lượng sang các instance còn lại mà không làm gián đoạn dịch vụ. Muốn giảm `p95`/`p99` của bản thân từng request `/ask`, ta phải tối ưu ở tầng LLM/RAG (semantic caching trên Redis, streaming response, dùng model nhỏ hơn hoặc rút gọn context) chứ không chỉ tăng số replica của web server.

---

## 6. Kết luận

- **3 điều học được về benchmark & observability:**
  1. **Percentile quan trọng hơn Average:** Latency trung bình (`avg`) che giấu hoàn toàn hiện tượng tail latency; chỉ khi đo `p95` và `p99` bằng load test (`load_test.py`, Locust) và Histogram trong Prometheus mới phát hiện được nhóm 3–10% người dùng đang phải chờ gần 2 giây.
  2. **Observability hạ tầng không thay thế được Quality Eval (và ngược lại):** Một bản cập nhật làm hỏng hoàn toàn logic trả lời (như tụt từ `v2` về `v1`, accuracy giảm từ 100% xuống 4.35%) vẫn có dashboard hạ tầng xanh toàn bộ. Bắt buộc phải có bộ `golden_dataset.jsonl` + quality gate trong CI/CD đi kèm chỉ số kinh tế `cost_per_correct_usd`.
  3. **Liên kết 3 trụ cột Metrics – Traces – Logs qua `trace_id`:** Metrics trên Grafana/Prometheus cho biết *khi nào* hệ thống bất thường (error rate, p95, cost burn rate vượt ngưỡng), Traces trên Jaeger chỉ rõ *span nào* gây chậm hoặc lỗi (`chat mock-llm-small` chiếm 98.53% thời gian), và `trace_id` trong structured JSON log cho phép truy xuất chính xác ngữ cảnh của từng request đó.
- **Nếu đưa agent này lên production thật, tôi sẽ thêm các metric và alert sau:**
  - **Metrics:**
    - `nginx_http_requests_total` / Ingress load-balancer metrics (để bắt các lỗi `502`/`504` xảy ra ở tầng gateway khi agent bị treo hoặc timeout mà metric bên trong agent không đếm được).
    - `agent_cache_hits_total` / `agent_cache_misses_total` và `redis_operation_duration_seconds` (giám sát hiệu quả cache và độ trễ của Redis cho rate limiter & cost guard).
    - `agent_eval_online_score` (điểm chất lượng chấm mẫu trực tuyến bằng LLM-as-a-judge) và `agent_retrieval_empty_ratio` (tỷ lệ truy vấn RAG không tìm thấy tài liệu phù hợp).
    - `llm_ttft_seconds` (Time To First Token khi bật streaming).
  - **Alerts:**
    - `AgentRetrievalMissRateHigh`: cảnh báo khi tỷ lệ `agent_retrieval_total{result="miss"}` vượt 30% trong 5 phút (dấu hiệu knowledge base thiếu tài liệu hoặc bộ embedding/vector DB gặp sự cố).
    - `Gateway5xxRateHigh`: cảnh báo từ tầng Nginx/Cloudflare khi tỷ lệ `502`/`504` > 1% trong 2 phút.
    - `DailyBudgetNearExhaustion`: cảnh báo sớm khi tổng chi phí trong Redis đạt 80% `DAILY_BUDGET_USD` trước khi người dùng bị chặn bởi HTTP `402`.
