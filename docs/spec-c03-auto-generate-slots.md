# C-03 场地时间段每日自动生成规范

## 版本: v1.0
## 日期: 2026-06-12
## 状态: 待实现

---

## 一、当前问题诊断

### 1.1 现状
- 已有手动批量生成接口 `POST /venues/{id}/slots/batch`
  - 文件：`backend/app/api/v1/venues.py:163-206`
- 无自动每日生成任务
- 管理员必须每天手动进入「时段管理」生成未来时段

### 1.2 缺失
| 缺失项 | 说明 |
|--------|------|
| 每日自动生成 Celery 任务 | 没有按场地营业时间自动补全未来时段 |
| 默认营业时间配置 | 场地模型未存储营业开始/结束时间 |
| 生成范围策略 | 未明确生成未来多少天 |

---

## 二、需求规格

### 2.1 自动生成策略
- 每日凌晨 02:00 执行 Celery beat 任务
- 为每个 `VenueStatus.active` 的场地生成未来 7 天的时段
- 默认营业时间：08:00 - 22:00
- 默认时段间隔：60 分钟
- 已存在的时段自动跳过（保证幂等）
- 新时段默认状态：`available`
- 价格使用场地 `price_per_hour`（不生成 price_override）

### 2.2 字段补充
为支持按场地自定义营业时间，在 `Venue` 模型增加：
```python
opening_time = Column(Time, default=time(8, 0), nullable=False)
closing_time = Column(Time, default=time(22, 0), nullable=False)
slot_interval_minutes = Column(Integer, default=60, nullable=False)
```

对应 schema 增加：
- `VenueCreate` / `VenueUpdate` / `VenueBrief` / `VenueDetail` 增加 `opening_time`、`closing_time`、`slot_interval_minutes`

### 2.3 任务实现
- 新建或扩展 `backend/app/tasks/tasks.py`
- 任务名：`app.tasks.tasks.generate_daily_slots`
- 在 `backend/app/tasks/worker.py` beat_schedule 中注册
- 任务逻辑：
  1. 查询所有 active venues
  2. 对每家 venue，生成从今天起未来 7 天（包含今天）的 slot
  3. 使用 ` VenueTimeSlot ` 唯一索引 `uq_slot` 跳过已存在记录
  4. 返回生成总数

---

## 三、API 变更

### 3.1 不新增 API
该功能为后台定时任务，无需新 API。

### 3.2 现有 API 扩展
- `POST /venues/{id}/slots/batch` 保持手动生成能力
-  venues 相关 schema 增加营业时间字段

---

## 四、数据库变更

```sql
ALTER TABLE venues
  ADD COLUMN opening_time TIME NOT NULL DEFAULT '08:00:00',
  ADD COLUMN closing_time TIME NOT NULL DEFAULT '22:00:00',
  ADD COLUMN slot_interval_minutes INT NOT NULL DEFAULT 60;
```

---

## 五、需要修改的文件

### 后端
- `backend/app/models/models.py` — `Venue` 增加营业时间字段
- `backend/app/schemas/schemas.py` — venues schema 增加字段
- `backend/app/tasks/tasks.py` — 新增 `generate_daily_slots` 任务
- `backend/app/tasks/worker.py` — 注册 beat schedule

### 前端（可选增强）
- `miniprogram/pages/publish/venue-manage.js` / `.wxml` — 支持编辑营业时间（本次至少 schema 支持）

---

## 六、验收标准

- [ ] `Venue` 模型包含 `opening_time`、`closing_time`、`slot_interval_minutes`
- [ ] Celery beat 每日 02:00 触发 `generate_daily_slots`
- [ ] 任务为每个 active venue 生成未来 7 天时段
- [ ] 已存在时段不重复生成
- [ ] 任务返回成功生成数量
- [ ] 手动批量生成接口仍正常工作
