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
| B-2 | `generate_slots` 接口未提交事务 | `app/api/v1/venues.py:206` | 管理员手动生成时段后数据未持久化 | 在返回前调用 `await db.commit()` | 🔄 待修复 |
| B-3 | `update_slot_status` 存在不可达死代码 | `app/api/v1/venues.py:240-252` | 返回 `dict` 而非声明的 `SlotBrief`，API 契约不一致 | 删除死代码或修复返回类型 | 🔄 待修复 |
| F-1 | `utils/request.js` 拒绝 201 | `miniprogram/utils/request.js:22` | 所有返回 201 的 POST/PUT 前端报错 | 改为 `res.statusCode >= 200 && res.statusCode < 300` | 🔄 待修复 |
| F-2 | `refreshTokenAndRetry` 无限递归 | `miniprogram/app.js:77-98` | refresh_token 过期或原请求再次 401 时栈溢出崩溃 | retry 请求带 `skipRefresh: true` | 🔄 待修复 |
| P-1 | 回调 nonce 去重存在竞态 | `app/api/v1/bookings.py:315-319` | 并发重试时可能重复处理同一回调 | 使用 Redis `SET NX EX` 原子操作 | 🔄 待修复 |

### 高优先级

| # | 问题 | 位置 | 影响 | 修复建议 | 状态 |
|---|------|------|------|----------|------|
| B-4 | `create_booking` 未显式提交 | `app/api/v1/bookings.py:66-156` | 依赖 get_db 隐式提交，存在不确定性 | 返回前 `await db.commit()` | 🔄 待修复 |
| B-5 | `generate_daily_slots` 重复时段会崩溃 | `app/tasks/tasks.py:95` | 若数据库已存在重复 slot，整个任务中断 | 使用 `scalars().first()` 或异常处理 | 🔄 待修复 |
| B-6 | `settlement.py` 未使用 `_v()` 比较枚举 | `app/services/settlement.py:45,49,210` | asyncmy 返回字符串，比较可能失败 | 使用 `_v()` 或字符串比较 | 🔄 待修复 |
| P-2 | 退款回调释放 slot 未校验所有权 | `app/services/payment_callback.py:196-206` | 可能误释放其他用户的新锁 | 校验 `slot.status == locked` 且 `slot.locked_by == order.user_id` | 🔄 待修复 |
| P-3 | 退款重试状态机不完善 | `app/tasks/tasks.py:253-262` | 可能将已成功的退款重新置为 processing | 调用 refund 后立即查询/处理响应状态 | 🔄 待修复 |
| F-3 | `confirm.js` 仅在 `onLoad` 检查登录 | `miniprogram/pages/booking/confirm.js` | 后台返回后可能处于未登录状态 | `onShow` 增加登录守卫 | 🔄 待修复 |
| F-4 | `my-bookings` 退款计算时区错误 | `miniprogram/pages/profile/my-bookings.js:136-139` | 用户设备时区与后端不一致时退款金额错误 | 后端返回 `slot_datetime` ISO 时间或 `refund_preview` | 🔄 待修复 |

### 中 / 低优先级

| # | 问题 | 位置 | 影响 | 修复建议 | 状态 |
|---|------|------|------|----------|------|
| B-7 | `process_callback` 多一层 `db.commit()` | `app/services/payment_callback.py:331` | 调用方也提交，可能双提交 | 移除 `process_callback` 内 commit | 🔄 待修复 |
| B-8 | `club_orders` 状态过滤传字符串 | `app/api/v1/bookings.py:663` | 可能因 asyncmy 类型问题过滤异常 | 校验后转 `OrderStatus(status)` | ⏳ 待安排 |
| B-9 | `release_expired_locks` 全表加载 locked slot | `app/tasks/tasks.py:27-33` | 高并发时内存/性能压力 | DB 层按 `locked_at` 过滤或分页 | ⏳ 待安排 |
| F-5 | `confirm.js` / `success.js` 后台计时器泄漏 | `confirm.js`, `success.js` | `onHide` 未清理计时器 | `onHide` 清理，`onShow` 恢复 | 🔄 待修复 |
| F-6 | `success.js` 无登录守卫和错误状态 | `miniprogram/pages/booking/success.js` | 未登录用户看到空白页 | 增加登录守卫和重试按钮 | 🔄 待修复 |
| F-7 | `wxpay.js` 错误对象未标准化 | `miniprogram/utils/wxpay.js:47-53` | 支付失败可能显示 undefined | `reject(new Error(err.errMsg || '支付失败'))` | 🔄 待修复 |
| F-8 | `wxpay.js` 未校验 `package` 前缀 | `miniprogram/utils/wxpay.js:8-16` | 非法 package 传入 requestPayment | 校验 `package.startsWith('prepay_id=')` | 🔄 待修复 |

### 时段生成任务失败调查

**根因**：`app/tasks/tasks.py` 模块顶部缺少 `from sqlalchemy import select, update`。P1-3 重构将任务内局部 `import select` 移除后，未在模块顶部补充，导致所有异步 Celery 任务（含 `generate_daily_slots`）运行时报 `NameError: name 'select' is not defined`。

**修复**：已于 hotfix `2267f23` 在模块顶部添加 `from sqlalchemy import select, update`，并验证导入与语法通过。

**验证命令**：
```bash
python -m py_compile app/tasks/tasks.py
python -c "from app.tasks.tasks import generate_daily_slots; print('import ok')"
```

## 结论与建议

- 已修复所有 P0/P1 评审问题，但上线前评审发现新的阻塞级问题（多由 P1-3 重构引入或之前未发现的 venues.py 问题）。
- 建议先修复所有标为 🔄 的阻塞/高优先级问题，再运行集成测试和 Celery worker 冒烟测试。
- 时段生成失败已定位并修复，需在测试环境部署后观察 Celery beat 日志确认时段正常生成。

## 变更日志

### 2026-06-14
- 开始上线前评审
- 定位时段生成失败根因：缺少 sqlalchemy 导入
- hotfix `2267f23` 修复 Celery 任务导入问题
