# 模块 B（预约 & 支付）上线前评审报告

## 评审日期
2026-06-14

## 评审范围
- 后端 API：`bookings.py`、`venues.py`、`tasks.py`、`settlement.py`、`payment_callback.py`、`models.py`、`rate_limit.py`
- 前端页面：`confirm.js/wxml/wxss`、`success.js/wxml/wxss`、`my-bookings.js/wxml`、`venue-detail.js/wxml`、`wxpay.js`、`app.js`
- WeChat 支付 V3 回调安全、Redis 分布式锁、Celery 异步任务

## 评审目标
确认模块 B 已修复 P0/P1 问题，达到可上线标准；识别剩余 P2/上线前问题；调查时段生成任务失败原因。

## 评审方法
1. 后端代码评审 Agent
2. 前端代码评审 Agent
3. 支付/安全专项评审 Agent
4. 时段生成任务专项调查

## 当前状态
- P0 阻断级问题：✅ 全部完成
- P1 高优先级问题：✅ 全部完成

## 发现的问题

### 严重 / 上线阻塞

| # | 问题 | 位置 | 影响 | 修复建议 | 状态 |
|---|------|------|------|----------|------|
| B-1 | Celery 任务缺少 `select`/`update` 导入 | `app/tasks/tasks.py:1-19` | 所有异步 Celery 任务运行时报 `NameError`，包括 `generate_daily_slots`、`release_expired_locks`、退款重试等 | 在模块顶部添加 `from sqlalchemy import select, update` | ✅ 已修复（hotfix 2267f23） |
| B-2 | `generate_slots` 接口未提交事务 | `app/api/v1/venues.py:206` | 管理员手动生成时段后数据未持久化 | 在返回前调用 `await db.commit()` | ✅ 已修复（ba17e95） |
| B-3 | `update_slot_status` 存在不可达死代码 | `app/api/v1/venues.py:240-252` | 返回 `dict` 而非声明的 `SlotBrief`，API 契约不一致 | 删除死代码并改为 PATCH 端点 | ✅ 已修复（ba17e95） |
| F-1 | `utils/request.js` 拒绝 201 | `miniprogram/utils/request.js:22` | 所有返回 201 的 POST/PUT 前端报错 | 改为 `res.statusCode >= 200 && res.statusCode < 300` | ✅ 已修复（1b8f68c） |
| F-2 | `refreshTokenAndRetry` 无限递归 | `miniprogram/app.js:77-98` | refresh_token 过期或原请求再次 401 时栈溢出崩溃 | retry 请求带 `skipRefresh: true` | ✅ 已修复（1b8f68c） |
| P-1 | 回调 nonce 去重存在竞态 | `app/api/v1/bookings.py:315-319` | 并发重试时可能重复处理同一回调 | 使用 Redis `SET NX EX` 原子操作 | ✅ 已修复（cb5709a） |

### 高优先级

| # | 问题 | 位置 | 影响 | 修复建议 | 状态 |
|---|------|------|------|----------|------|
| B-4 | `create_booking` 未显式提交 | `app/api/v1/bookings.py:66-156` | 依赖 get_db 隐式提交，存在不确定性 | 返回前 `await db.commit()` | ✅ 已修复（cb5709a） |
| B-5 | `generate_daily_slots` 重复时段会崩溃 | `app/tasks/tasks.py:95` | 若数据库已存在重复 slot，整个任务中断 | 使用 `scalars().first()` | ✅ 已修复（d8892e6） |
| B-6 | `settlement.py` 未使用 `_v()` 比较枚举 | `app/services/settlement.py:45,49,210` | asyncmy 返回字符串，比较可能失败 | 使用 `_v()` | ✅ 已修复（d8892e6） |
| P-2 | 退款回调释放 slot 未校验所有权 | `app/services/payment_callback.py:196-206` | 可能误释放其他用户的新锁 | 校验 `slot.status == locked` 且 `slot.locked_by == order.user_id` | ✅ 已修复（d8892e6） |
| P-3 | 退款重试状态机不完善 | `app/tasks/tasks.py:253-262` | 可能将已成功的退款重新置为 processing | 调用 refund 后按响应状态更新 | ✅ 已修复（d8892e6） |
| F-3 | `confirm.js` 仅在 `onLoad` 检查登录 | `miniprogram/pages/booking/confirm.js` | 后台返回后可能处于未登录状态 | `onShow` 增加登录守卫 | ✅ 已修复（816791e） |
| F-4 | `my-bookings` 退款计算时区错误 | `miniprogram/pages/profile/my-bookings.js:136-139` | 用户设备时区与后端不一致时退款金额错误 | 后端返回 `slot_datetime` ISO 时间 | ✅ 已修复（816791e） |

| # | 问题 | 位置 | 影响 | 修复建议 | 状态 |
|---|------|------|------|----------|------|
| B-10 | 退款回调未释放 `booked` slot | `app/services/payment_callback.py:196-207` | 退款成功后场地永久显示已预约 | 释放 `locked` 和 `booked` 且无其他活跃订单的 slot | ✅ 已修复（e36b5e6） |
| B-11 | `_update_order_after_refund` 无条件释放 slot | `app/tasks/tasks.py:181-201` | 可能误释放被其他用户预订的 slot | 加所有权/状态校验 | ✅ 已修复（e36b5e6） |
| B-12 | 分账查询失败回滚 `processing` 状态 | `app/tasks/tasks.py:145-154` / `app/api/v1/bookings.py:782-799` | 重复创建微信分账订单 | `execute_settlement` 后立即 `commit` | ✅ 已修复（4c6498f） |
| B-13 | `cancel_booking` / `refund_booking` 无行锁 | `app/api/v1/bookings.py:349-474`, `477+` | 并发取消/退款产生重复退款 | 添加 `.with_for_update()` | ✅ 已修复（a9b8c2a） |
| B-14 | `create_booking` 提交后异常误放锁 | `app/api/v1/bookings.py:66-156` | DB-Redis 状态不一致 | `return` 移出 try/except | ✅ 已修复（a9b8c2a） |
| F-9 | `confirm.js` 无 `options` 空值保护 | `miniprogram/pages/booking/confirm.js:34` | 无参数进入页面崩溃 | `options = options \|\| {}` | ✅ 已修复（2aeaf9b） |
| F-10 | `success.js` 缺少 `onUnload` 清理轮询 | `miniprogram/pages/booking/success.js` | 页面销毁后仍轮询 | 添加 `onUnload` | ✅ 已修复（2aeaf9b） |
| F-11 | `confirm.js` `onShow` 用空值拼 redirect | `miniprogram/pages/booking/confirm.js:54` | 登录回跳 URL 错误 | slotId 存在时才拼完整 URL | ✅ 已修复（2aeaf9b） |
| F-12 | URL 参数未编码 | `confirm.js`, `club-list.js` | 名称含特殊字符时 URL 错误 | `encodeURIComponent` | ✅ 已修复（2aeaf9b） |
| F-13 | `wxpay.js` `errMsg` 可能 undefined | `miniprogram/utils/wxpay.js` | 空指针异常 | 加 `errMsg &&` 保护 | ✅ 已修复（2aeaf9b） |
| P-4 | 赛事支付无速率限制 | `app/api/v1/tournaments.py:272` | 可刷单/DoS | 添加 `check_rate_limit` | ✅ 已修复（c023839） |
| P-5 | `create_booking` 无速率限制 | `app/api/v1/bookings.py:66` | 批量锁定不同 slot | 添加 `check_rate_limit` | ✅ 已修复（c023839） |

| B-15 | `tasks.py` 缺少 `_v` 导入 | `app/tasks/tasks.py:1-20` | Celery 退款任务运行时报 `NameError` | 添加 `from app.api.deps import _v` | ✅ 已修复（ec11b50） |

| B-16 | Docker Compose `REDIS_URL` 指向 MySQL 端口 | `docker-compose.yml:22` | Redis 连接失败，锁/限流/Celery 全失效 | 改为 `redis://:${REDIS_PASSWORD:-redis_pass}@redis:6379/0` | ✅ 已修复（91f767e） |
| B-17 | Docker Compose 缺少 Celery worker/beat | `docker-compose.yml` | 时段释放、结算、退款重试均不执行 | 添加 `celery_worker` 和 `celery_beat` 服务 | ✅ 已修复（91f767e） |
| B-18 | `.env.example` 缺少结算/退款/限流配置 | `backend/.env.example` | 运维无法获知全部可调参数 | 补充相关环境变量 | ✅ 已修复（ee38892） |

| B-19 | Celery beat 任务名与注册名不匹配 | `app/tasks/worker.py:21,25` | beat 触发时 `NotRegistered` 错误 | 统一使用 `app.tasks.tasks.*` 全限定名 | ✅ 已修复（c96b106） |
| B-20 | `tasks.py` 缺少 `logger` 定义 | `app/tasks/tasks.py` | `logger.exception` 调用报 `NameError` | 添加 `logger = logging.getLogger(__name__)` | ✅ 已修复（c96b106） |

| B-21 | `venues.py` 缺少 `_slot_to_brief` | `app/api/v1/venues.py:124` | `get_slots` 运行时报 `NameError` | 补全 `_slot_to_brief` 函数 | ✅ 已修复（421d55d） |
| B-22 | 回调时间戳未处理非数字 | `app/api/v1/bookings.py:315` | 非法时间戳导致 500 | `try/except` 返回 400 | ✅ 已修复（421d55d） |
| B-23 | 赛事支付金额截断 | `app/api/v1/tournaments.py:322` | `int(amount*100)` 可能少 1 分 | 使用 `_to_cents()` | ✅ 已修复（421d55d） |
| B-24 | Celery 任务名仍不匹配 | `app/tasks/tasks.py:67,120` / `worker.py:21,25` | beat 触发 `NotRegistered` | 装饰器与 schedule 统一全限定名 | ✅ 已修复（421d55d） |
| B-25 | 赛事订单 `slot_id` 非空冲突 | `app/models/models.py` | 赛事报名创建订单时 `slot_id=None` 违反约束 | `slot_id` 改为 `nullable=True` | ✅ 已修复（421d55d） |
| B-26 | 赛事时段时区比较异常 | `app/api/v1/tournaments.py:350` | naive/aware 时间比较 `TypeError` | 统一转换为 naive | ✅ 已修复（421d55d） |
| F-14 | `confirm.js` price 存为字符串 | `miniprogram/pages/booking/confirm.js:41` | 数值类型不一致 | data 存 number，WXML 用 `toFixed(2)` | ✅ 已修复（8c4e608） |
| F-15 | `success.js` pollCount 未重置 | `miniprogram/pages/booking/success.js` | 多次进入提前停止轮询 | `onShow` 重置 `pollCount` | ✅ 已修复（8c4e608） |
| F-16 | `success.js` 轮询并发风险 | `miniprogram/pages/booking/success.js:65` | 可能同时运行多轮询 | 加 `if (!this.data.polling) return` | ✅ 已修复（8c4e608） |
| F-17 | `my-bookings` 无 slot_datetime 兼容 | `miniprogram/pages/profile/my-bookings.js:136` | 后端未返回时退款计算失败 | fallback 到 `slot_date` + `slot_start` | ✅ 已修复（8c4e608） |
| F-18 | `venue-detail` maintenance 无标签 | `miniprogram/pages/booking/venue-detail.wxml:92` | 用户看不到维护状态 | 添加 "维护中" 标签和样式 | ✅ 已修复（8c4e608） |
| F-19 | 下拉刷新可能不停止 | `my-bookings.js`, `club-list.js` | 加载失败时刷新指示器卡住 | `.then` 加 rejection handler | ✅ 已修复（8c4e608） |
| D-1 | `.env.example` Redis URL 无密码 | `backend/.env.example:9` | 与 docker-compose 密码要求不一致 | 改为带密码 URL | ✅ 已修复（91cc319） |
| D-2 | `.env.example` 缺少 `REDIS_PASSWORD` | `backend/.env.example` | 运维不知道要配置 | 添加 `REDIS_PASSWORD` | ✅ 已修复（91cc319） |
| D-3 | MySQL healthcheck 未接入 depends_on | `docker-compose.yml` | 服务可能在 MySQL 就绪前启动 | 使用 `condition: service_healthy` | ✅ 已修复（91cc319） |

### 中 / 低优先级

_无剩余中/低优先级问题。_

| # | 问题 | 位置 | 影响 | 修复建议 | 状态 |
|---|------|------|------|----------|------|
| B-7 | `process_callback` 多一层 `db.commit()` | `app/services/payment_callback.py:331` | 调用方也提交，可能双提交 | 移除 `process_callback` 内 commit | ✅ 已修复（dca3793） |
| B-8 | `club_orders` 状态过滤传字符串 | `app/api/v1/bookings.py:663` | 可能因 asyncmy 类型问题过滤异常 | 校验后转 `OrderStatus(status)` | ✅ 已修复（8d5ffc9） |
| B-9 | `release_expired_locks` 全表加载 locked slot | `app/tasks/tasks.py:27-33` | 高并发时内存/性能压力 | DB 层按 `locked_at` 过滤 | ✅ 已修复（8d5ffc9） |
| F-5 | `confirm.js` / `success.js` 后台计时器泄漏 | `confirm.js`, `success.js` | `onHide` 未清理计时器 | `onHide` 清理，`onShow` 恢复 | ✅ 已修复（0ee4abe） |
| F-6 | `success.js` 无登录守卫和错误状态 | `miniprogram/pages/booking/success.js` | 未登录用户看到空白页 | 增加登录守卫和重试按钮 | ✅ 已修复（0ee4abe） |
| F-7 | `wxpay.js` 错误对象未标准化 | `miniprogram/utils/wxpay.js:47-53` | 支付失败可能显示 undefined | `reject(new Error(err.errMsg || '支付失败'))` | ✅ 已修复（0ee4abe） |
| F-8 | `wxpay.js` 未校验 `package` 前缀 | `miniprogram/utils/wxpay.js:8-16` | 非法 package 传入 requestPayment | 校验 `package.startsWith('prepay_id=')` | ✅ 已修复（0ee4abe） |

### 时段生成任务失败调查

**根因**：`app/tasks/tasks.py` 模块顶部缺少 `from sqlalchemy import select, update`。P1-3 重构将任务内局部 `import select` 移除后，未在模块顶部补充，导致所有异步 Celery 任务（含 `generate_daily_slots`）运行时报 `NameError: name 'select' is not defined`。

**修复**：已于 hotfix `2267f23` 在模块顶部添加 `from sqlalchemy import select, update`，并验证导入与语法通过。

**验证命令**：
```bash
python -m py_compile app/tasks/tasks.py
python -c "from app.tasks.tasks import generate_daily_slots; print('import ok')"
```

### P2 问题处理

| # | 问题 | 位置 | 影响 | 修复建议 | 状态 |
|---|------|------|------|----------|------|
| P2-1 | `BookingOrder.order_no` 缺少索引 | `app/models/models.py` | 回调查询、订单查询全表扫描 | 添加 `index=True` | ✅ 已修复（4136a74） |
| P2-2 | `refund_status` 使用 String 而非 Enum | `app/models/models.py` | 缺少 DB 约束，可能出现非法值 | 改为 `Enum(RefundStatus, native_enum=False)` | ✅ 已修复（4136a74） |
| P2-3 | `_refund_slot_release` 死代码 | `app/api/v1/bookings.py` | 维护负担 | 删除 | ✅ 已修复（4136a74） |
| P2-5 | `venue-detail` 未区分 locked/booked 视觉状态 | `miniprogram/pages/booking/venue-detail.wxml/wxss` | 用户无法区分 | 分别显示 "已预约" / "锁定中" 并加样式 | ✅ 已修复（4136a74） |
| P2-4 | `update_slot_status` 死/不可达代码 | `app/api/v1/venues.py:240-252` | 逻辑错误 | 已随 B-3 修复 |
| P2-6 | `club-list` 缺少 `onReachBottom` 分页 | `miniprogram/pages/booking/club-list.js` | 只能显示前 20 条 | 添加分页 | ✅ 已修复（bf0ae26） |
| P2-7 | `club-detail` 是空占位符 | `miniprogram/pages/booking/club-detail.js/wxml` | 页面不可用 | 移除空页面及 app.json 注册 | ✅ 已修复（bf0ae26） |
| P2-8 | `venue-detail/club-list` 导航命名混乱 | `miniprogram/pages/booking/club-list.js:107` | 可读性差 | 添加注释说明 venue-detail 为俱乐部预订页 | ✅ 已修复（bf0ae26） |
| P2-9 | 文档与实现不同步 | `docs/workflow-backend-api.md` | 新开发者误解 | 重写 booking/payment/refund/settlement 流程 | ✅ 已修复（319726f） |

## 结论与建议

- 已修复所有 P0/P1 评审问题。
- 上线前评审及多轮复查发现的所有阻塞/高优先级问题已全部修复。
- **第七轮修复**：
  - 后端：补全 `_slot_to_brief`、回调时间戳校验、赛事金额 `_to_cents`、Celery 任务名统一、赛事订单 `slot_id` nullable、赛事时段时区比较
  - 前端：`confirm.js` price 类型、`success.js` 轮询重置与并发保护、`my-bookings` slot 时间 fallback、`venue-detail` 维护标签、下拉刷新清理
  - 部署：`.env.example` Redis 密码一致、`REDIS_PASSWORD` 变量、MySQL healthcheck 接入 depends_on
- 后端、前端、支付安全、集成/部署评审均通过。
- 当前模块后端 31 项测试全部通过，工作区干净。
- 建议下一步：在测试环境执行 `docker-compose up -d` 启动完整栈，跑通创建订单 → 支付 → 退款 → 结算全链路。

## 变更日志

### 2026-06-15（第七轮）
- 后端/前端/部署最终扫描发现并修复剩余问题：
  - 后端：`_slot_to_brief` 缺失、回调时间戳非法值、赛事 `_to_cents`、Celery 任务名、赛事 `slot_id` nullable、赛事时区比较（421d55d）
  - 前端：`confirm.js` price 类型、`success.js` 轮询、`my-bookings` slot 时间 fallback、维护标签、下拉刷新（8c4e608）
  - 部署：Redis 密码一致性、`REDIS_PASSWORD`、MySQL healthcheck depends_on（91cc319）
- 31 项后端测试全部通过
- 更新 `module-b-production-readiness.md` 和 `module-b-fix-progress.md`

### 2026-06-15（第六轮）
- 复查发现退款回调未释放 `booked` slot（BLOCKER），已修复（e36b5e6）
- 修复 `_update_order_after_refund` 无条件释放 slot 的竞态（e36b5e6）
- 修复分账 `execute_settlement` 与 `query_settlement_status` 之间的提交边界（4c6498f）
- 为 `cancel_booking` / `refund_booking` 添加 `.with_for_update()`（a9b8c2a）
- 修复 `create_booking` 提交后异常误放 Redis 锁（a9b8c2a）
- 修复前端 `confirm.js` / `success.js` / `club-list.js` / `wxpay.js` 边界问题（2aeaf9b）
- 为 `pay_tournament` 和 `create_booking` 添加速率限制（c023839）
- 修复因新增限流导致的 `create_booking` 测试（a6f5972）
- 31 项后端测试全部通过
- 更新 `module-b-production-readiness.md` 和 `module-b-fix-progress.md`

### 2026-06-15（本轮）
- 复查发现 `refund_booking` 缺少路由装饰器并修复（cbded9c）
- 修复 `club-list` 分页、移除空 `club-detail` 页面、添加导航注释（bf0ae26）
- 同步 `docs/workflow-backend-api.md` 至当前实现（319726f）
- 更新 `module-b-production-readiness.md` 和 `module-b-fix-progress.md`
- 31 项后端测试全部通过

### 2026-06-15
- 完成所有 P1 高优先级问题修复
- 完成上线前评审发现的所有阻塞/高/中优先级问题修复
- 完成 B-8/B-9 及 P2-1/P2-2/P2-3/P2-5 优化
- 31 项后端测试全部通过
- 工作区已提交至 git，无未提交变更

### 2026-06-14
- 开始上线前评审
- 定位时段生成失败根因：缺少 sqlalchemy 导入
- hotfix `2267f23` 修复 Celery 任务导入问题
