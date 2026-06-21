# C-07 俱乐部曝光与浏览量统计规范

## 版本: v1.0

## 日期: 2026-06-12

## 状态: 待实现

---

## 一、当前问题诊断

### 1.1 现状

- `Club` 模型无浏览/曝光字段
- `GET /clubs/{id}/stats` 已存在，返回：总场地数、总订单数、总收入、今日订单、今日收入
- club-dashboard 页面已展示部分统计

### 1.2 缺失


| 缺失项      | 说明                    |
| -------- | --------------------- |
| 浏览量字段    | `Club.view_count`     |
| 曝光量字段    | `Club.exposure_count` |
| 浏览自动递增   | 访问详情/列表时未计数           |
| 曝光统计 API | 无独立曝光/浏览查询接口          |
| 前端展示     | dashboard 未展示浏览/曝光    |


---

## 二、需求规格

### 2.1 数据模型

`Club` 增加字段：

```python
view_count = Column(BigInteger, default=0, nullable=False)
exposure_count = Column(BigInteger, default=0, nullable=False)
```

### 2.2 统计口径

- **view_count（浏览量）**: 用户进入俱乐部详情页 `GET /clubs/{id}` 时 +1
  - 同一用户 5 分钟内重复访问只计 1 次（使用 Redis 去重）
  - Key: `club:view:{club_id}:{user_id}:{yyyy-mm-dd-hh-mm/5min}`
- **exposure_count（曝光量）**: 俱乐部卡片出现在列表 `GET /clubs` 结果中并返回给用户时 +1
  - 同一用户每次列表请求中每个 club 只计 1 次
  - 不依赖用户登录：未登录用户使用 session 标识（此处使用 user_id 或 openid，未登录则跳过）

### 2.3 简化实现

第一期简化：

- 浏览量：`GET /clubs/{id}` 每次调用 +1（不去重）
- 曝光量：`GET /clubs` 返回列表时，对每个 club +1（不去重）
- 后续可加入 Redis 去重

### 2.4 API 变更

`ClubBrief` / `ClubDetail` 增加：

```python
view_count: int = 0
exposure_count: int = 0
```

`ClubStats` 增加：

```python
view_count: int
exposure_count: int
```

### 2.5 前端

- `club-dashboard.wxml` 增加浏览量/曝光量卡片
- `club-list.wxml` 可选展示热度（view_count）

---

## 三、数据库变更

```sql
ALTER TABLE clubs
  ADD COLUMN view_count BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN exposure_count BIGINT NOT NULL DEFAULT 0;
```

---

## 四、需要修改的文件

### 后端

- `backend/app/models/models.py` — `Club` 增加 `view_count`、`exposure_count`
- `backend/app/schemas/schemas.py` — `ClubBrief`、`ClubDetail`、`ClubStats` 增加字段
- `backend/app/api/v1/clubs.py` — 列表和详情接口递增计数

### 前端

- `miniprogram/pages/profile/club-dashboard.wxml` — 展示浏览/曝光
- `miniprogram/pages/booking/club-list.wxml` — 可选热度标签

---

## 五、验收标准

- `Club` 模型包含 `view_count` 和 `exposure_count`
- 访问 `GET /clubs/{id}` 后 `view_count` +1
- 访问 `GET /clubs` 后返回的每个 club `exposure_count` +1
- `ClubStats` 返回浏览量/曝光量
- club-dashboard 页面展示浏览量/曝光量
- 接口返回包含新增字段

