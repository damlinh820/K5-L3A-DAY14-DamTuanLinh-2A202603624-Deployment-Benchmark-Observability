# Part 4 — Bằng chứng HTTP localhost

Ngày kiểm tra: 2026-11-25. Chạy app mẫu trong `04-api-gateway/` bằng Python 3.11.9 trên localhost. Token JWT không được ghi vào file này.

## API key (`develop/app.py`)

```text
POST /ask, không có X-API-Key      → HTTP/1.1 401 Unauthorized
POST /ask, X-API-Key demo hợp lệ   → HTTP 200; body có question="Hello" và answer
```

## JWT và rate limit (`production/app.py`)

```text
POST /ask, không có Bearer token           → 401
POST /auth/token, demo user hợp lệ         → 200
POST /ask, Bearer token hợp lệ, request 1  → 200
POST /ask, Bearer token hợp lệ, request 10 → 200
POST /ask, Bearer token hợp lệ, request 11 → 429
POST /ask, request kế tiếp                 → 429; Retry-After: 48
```

Các request dùng body JSON `{"question":"Explain JWT"}`. Mẫu dùng sliding window 10 request/60 giây cho user; giá trị `Retry-After` phụ thuộc thời điểm chạy.

## Cost guard

Kiểm thử trực tiếp class `CostGuard` với budget thử nghiệm `$0.000001`: sau khi ghi 1.000 input và 1.000 output token, `check_budget()` ném `HTTPException: 402`, `used_usd=0.00075`. Đây là kiểm tra logic class; không phải HTTP response từ endpoint đang chạy.

## Giới hạn bằng chứng

Các status trên được lấy từ app mẫu trên localhost. Chưa có URL production để kiểm tra cùng luồng trên cloud. API key và JWT trong bài thử chỉ là dữ liệu demo; không lưu token thật.
