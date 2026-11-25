# Part 5 — Bằng chứng scaling và reliability

Ngày kiểm tra: 2026-11-25. Docker Compose project `k5-day14-scaling`, 3 agent + Redis + Nginx, truy cập qua `http://localhost:8080`.

```text
GET /health khi Redis hoạt động → 200; status=ok; storage=redis; redis_connected=true
GET /ready khi Redis hoạt động  → 200; ready=true

test_stateless.py:
  5 request /chat cùng session
  served_by: instance-696161, instance-249310, instance-9be20b
  GET /chat/{session_id}/history → count=10

docker stop k5-day14-scaling-agent-2:
  exit code=0; status=exited
  log: Shutting down → Instance ... shutting down → Application shutdown complete

POST /chat sau khi dừng một agent → thành công; served_by=instance-9be20b; storage=redis
GET /chat/{session_id}/history → count=12

docker stop k5-day14-scaling-redis-1:
  GET /health qua Nginx → 200; status=degraded; redis_connected=false
  GET /ready trực tiếp trong agent → 503
  GET /ready qua Nginx → 502 (Nginx thử lại các upstream 503)

docker start k5-day14-scaling-redis-1:
  GET /ready qua Nginx → 200
```

Session ID đã được lược bỏ khỏi bằng chứng; đây là dữ liệu thử nghiệm. Chưa có phép thử request đang xử lý khi nhận SIGTERM.
