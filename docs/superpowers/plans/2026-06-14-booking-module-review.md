# 订场地模块多轮 Review 计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement review tasks. Steps use checkbox syntax.

**Goal:** 对「订场地」模块（俱乐部列表、场地详情、时段选择、下单、支付、支付成功、我的预约）进行多维度交叉评审，汇总问题清单并按 P0/P1/P2 分级。

**Scope:**
- Frontend: `miniprogram/pages/booking/*`（club-list, club-detail, venue-detail, confirm, success, my-bookings）
- Backend: `backend/app/api/v1/bookings.py`, `backend/app/api/v1/venues.py`, `backend/app/api/v1/clubs.py` 中订场相关接口
- Models: `backend/app/models/models.py` 中 BookingOrder / VenueTimeSlot / SettlementRecord 等
- Tasks: `backend/app/tasks/tasks.py`, `backend/app/tasks/worker.py`
- WeChat Pay: `backend/app/core/wechat_pay.py`
- Config/Schema: `backend/app/core/config.py`, `backend/app/schemas/schemas.py`
- Docs: `docs/workflow-backend-api.md`, `docs/module-b-review-report.md`, `docs/module-b-fix-progress.md`

---

## Review Dimensions

### Round 1: Backend API & Data Model
**Focus:** 接口正确性、并发安全、数据一致性、幂等性、状态机、时区/金额计算

- [ ] **Task 1.1: Booking API audit**
  - Files: `backend/app/api/v1/bookings.py`
  - Check: slot lock lifecycle, payment callback idempotency, refund/cancel timezone math, settlement integration, race conditions
- [ ] **Task 1.2: Venue/Club API audit**
  - Files: `backend/app/api/v1/venues.py`, `backend/app/api/v1/clubs.py`
  - Check: slot generation/toggle, LBS distance, authorization, pricing exposure
- [ ] **Task 1.3: Model & Schema audit**
  - Files: `backend/app/models/models.py`, `backend/app/schemas/schemas.py`
  - Check: enum usage, defaults, indexes, nullable constraints, schema/response consistency

### Round 2: Frontend UX & Logic
**Focus:** 页面状态、错误处理、登录前置、数据绑定、导航参数、微信 API 使用

- [ ] **Task 2.1: Club/Venue list pages**
  - Files: `miniprogram/pages/booking/club-list.js/wxml/wxss`, `club-detail.*`
  - Check: list filters, distance display, empty/loading states, image fallback
- [ ] **Task 2.2: Venue detail & slot selection**
  - Files: `miniprogram/pages/booking/venue-detail.js/wxml/wxss`
  - Check: date switching, slot status visual distinction (locked/booked/available), price display, login guard
- [ ] **Task 2.3: Confirm & Success pages**
  - Files: `miniprogram/pages/booking/confirm.*`, `success.*`
  - Check: order summary, payment button, countdown, polling, navigation back behavior
- [ ] **Task 2.4: My bookings page**
  - Files: `miniprogram/pages/profile/my-bookings.*`
  - Check: status tabs, pay-now/cancel-refund buttons, refund preview, login guard

### Round 3: Payment, Security & Concurrency
**Focus:** 微信支付 V3 最佳实践、签名/回调、Redis 锁、Celery 任务、资金安全

- [ ] **Task 3.1: WeChat Pay integration audit**
  - Files: `backend/app/core/wechat_pay.py`, `backend/app/api/v1/bookings.py` (pay/notify)
  - Check: prepay_id reuse, callback signature verification, amount precision, refund idempotency
- [ ] **Task 3.2: Redis lock & Celery audit**
  - Files: `backend/app/core/redis.py`, `backend/app/tasks/tasks.py`, `worker.py`
  - Check: lock ownership, TTL, release on timeout, asyncio loop, beat schedules
- [ ] **Task 3.3: Security & authorization audit**
  - Files: `backend/app/api/deps.py`, relevant booking endpoints
  - Check: role checks, resource ownership, exposed sensitive fields

### Round 4: Integration & Cross-Validation
**Focus:** 端到端流程、文档同步、P0/P1/P2 分级、修复建议

- [ ] **Task 4.1: End-to-end flow review**
  - Simulate: select club → venue → date → slot → confirm → pay → success → my bookings → cancel/refund
  - Identify blockers and inconsistencies
- [ ] **Task 4.2: Documentation sync check**
  - Files: `docs/workflow-backend-api.md`, `docs/module-b-fix-progress.md`
  - Check: documented flows match implementation, outdated limitations, missing admin endpoints
- [ ] **Task 4.3: Consolidate findings**
  - Merge duplicate issues, assign severity, produce actionable report

---

## Deliverables

1. `docs/module-b-review-report-v2.md` — P0/P1/P2 问题清单 + 修复建议
2. `docs/module-b-fix-progress.md` update — 新增/更新问题跟踪行
3. Optional: quick fixes for obvious P0 blockers (with subagent implementation + review)

---

## Review Rules

- Each reviewer reads actual code, not summaries.
- Cite file:line for every issue.
- Distinguish confirmed bugs from assumptions/speculation.
- Cross-check against WeChat Pay V3 docs and Redis/Celery best practices.
- Keep each review focused on one dimension; do not duplicate work.
