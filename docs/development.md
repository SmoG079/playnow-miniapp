# 开发文档

## 1. 技术选型

| 层面 | 选型 | 说明 |
|------|------|------|
| 小程序前端 | 原生微信小程序 (WXML/WXSS/JS) | 体积最小，微信生态集成最深 |
| 后端 API | Python FastAPI + Gunicorn + Uvicorn | 异步高性能，Pydantic 类型安全 |
| 数据库 | MySQL 8.0 | 事务强，适合订单/分账场景 |
| 缓存/锁 | Redis 7 | 场地分布式锁、会话、热点数据缓存 |
| 对象存储 | CloudFlareR2 (腾讯云COS？) | 俱乐部图片、用户头像 |
| 部署 | 云服务器 + Docker Compose | 可控、无锁定、成本低 |
| 反向代理 | Nginx + SSL (Let's Encrypt) | HTTPS 终端 + 静态资源 |
| 支付 | 微信支付 V3 API + 分账 | JSAPI 支付，官方分账能力 |
| 消息推送 | 微信订阅消息 | 预约确认、开赛提醒 |
| IM / 客服 | 微信客服 + 微信群聊开放能力 | 轻量，无需自建 IM |

## 2. 服务器配置

| 阶段 | 配置 | 服务器 | 费用参考 |
|------|------|--------|----------|
| MVP | 4C4G+3M+40G SSD | 腾讯Lighthouse | 100元/年 |
| 成长期 | 4C8G+3M+50G SSD | 腾讯CVM | 1000元/年 |
| 规模化 | 4C8G × 2（负载均衡） | 腾讯CVM | 2000元/年 |

## 3. 数据库设计

### 核心表结构

- `users` - 用户表
- `clubs` - 俱乐部表
- `club_members` - 俱乐部-管理员关联
- `venues` - 场地表
- `venue_time_slots` - 场地时间段
- `booking_orders` - 预约订单
- `settlement_records` - 分账记录
- `match_posts` - 约球帖
- `match_registrations` - 约球报名
- `tournaments` - 比赛
- `tournament_registrations` - 比赛报名
- `notifications` - 系统通知

### ER 图关系

```
users ──< club_members >── clubs
clubs ──< venues
venues ──< venue_time_slots
venues ──< booking_orders
users ──< booking_orders
users ──< match_posts
users ──< match_registrations
users ──< tournament_registrations
clubs ──< tournaments
tournaments ──< tournament_registrations
venues ──< tournaments
match_posts ──< match_registrations
booking_orders ──< settlement_records
clubs ──< notifications
users ──< notifications
```

### 用户表 (users)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK AUTO_INCREMENT | |
| openid | VARCHAR(64) NOT NULL UNIQUE | |
| unionid | VARCHAR(64) | |
| nickname | VARCHAR(64) | |
| avatar_url | VARCHAR(512) | |
| phone | VARCHAR(20) | |
| role | ENUM('user','club_admin','platform_admin') DEFAULT 'user' | |
| created_at | DATETIME DEFAULT CURRENT_TIMESTAMP | |
| updated_at | DATETIME ON UPDATE CURRENT_TIMESTAMP | |

### 俱乐部表 (clubs)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK AUTO_INCREMENT | |
| name | VARCHAR(128) NOT NULL | |
| sport_types | VARCHAR(256) | JSON array |
| description | TEXT | |
| cover_image | VARCHAR(512) | |
| images | TEXT | JSON array, 多图 |
| address | VARCHAR(256) | |
| latitude | DECIMAL(10,7) | |
| longitude | DECIMAL(10,7) | |
| contact_phone | VARCHAR(20) | |
| split_ratio | DECIMAL(4,3) DEFAULT 0.100 | 平台抽成比例 |
| sub_merchant_id | VARCHAR(64) | 微信子商户号 |
| status | ENUM('active','inactive') DEFAULT 'active' | |
| created_at | DATETIME DEFAULT CURRENT_TIMESTAMP | |
| updated_at | DATETIME ON UPDATE CURRENT_TIMESTAMP | |

### 其他核心表（场地、订单、约球帖、比赛等）

详见数据库完整结构，核心包含：venues、venue_time_slots、booking_orders、settlement_records、match_posts、match_registrations、tournaments、tournament_registrations、notifications。

## 4. API 设计

**Base URL**: `https://api.your-domain.com/api/v1`

### 认证接口
- `POST /auth/login` - 微信登录 (code → jwt)
- `POST /auth/refresh` - 刷新 token
- `POST /auth/phone` - 微信手机号解密

### 用户接口
- `GET /users/me` - 我的信息
- `PUT /users/me` - 更新资料
- `GET /users/me/bookings` - 我的预约
- `GET /users/me/registrations` - 我的报名
- `GET /users/me/posts` - 我发布的约球帖
- `GET /users/me/notifications` - 我的通知

### 俱乐部接口
- `GET /clubs` - 俱乐部列表（支持 LBS、运动类型筛选）
- `GET /clubs/:id` - 俱乐部详情
- `POST /clubs` - 创建俱乐部
- `PUT /clubs/:id` - 编辑（需 club_admin）
- `GET /clubs/:id/venues` - 俱乐部下场地列表
- `GET /clubs/:id/posts` - 俱乐部约球帖
- `GET /clubs/:id/tournaments` - 俱乐部比赛
- `GET /clubs/:id/orders` - 俱乐部订单（需 club_admin）
- `GET /clubs/:id/settlements` - 分账记录（需 club_admin）
- `GET /clubs/:id/stats` - 统计概览（需 club_admin）

### 场地接口
- `GET /venues/:id` - 场地详情
- `POST /venues` - 创建场地（需 club_admin）
- `PUT /venues/:id` - 编辑场地（需 club_admin）
- `DELETE /venues/:id` - 删除场地（需 club_admin）
- `GET /venues/:id/slots` - 获取时间段
- `POST /venues/:id/slots/batch` - 批量生成时间段（需 club_admin）
- `PUT /venues/:id/slots/batch` - 批量更新时间段状态（需 club_admin）

### 预约接口
- `POST /bookings` - 创建预约（锁场 + 生成预订单）
- `POST /bookings/:id/pay` - 发起支付
- `GET /bookings/:id` - 预约详情
- `POST /bookings/:id/cancel` - 取消预约
- `POST /bookings/wx-notify` - 微信支付回调（无需鉴权）

### 约球帖接口
- `GET /posts` - 约球帖列表
- `POST /posts` - 发布约球帖
- `GET /posts/:id` - 详情（含报名列表）
- `POST /posts/:id/register` - 报名
- `DELETE /posts/:id/register` - 取消报名
- `PUT /posts/:id/registrations/:uid` - 审核（帖主）

### 比赛接口
- `GET /tournaments` - 比赛列表
- `POST /tournaments` - 创建比赛（需 club_admin）
- `PUT /tournaments/:id` - 编辑比赛（需 club_admin）
- `GET /tournaments/:id` - 详情
- `POST /tournaments/:id/register` - 报名

### 公共服务
- `POST /upload` - 图片上传 (→ OSS)
- `GET /config` - 小程序全局配置

### 鉴权中间件层级

```
公开接口 → 登录用户 → 俱乐部管理员 → 平台超管
```

## 5. 前端页面结构

```
miniprogram/
├── app.js / app.json / app.wxss
├── custom-tab-bar/               # 自定义 TabBar
├── pages/
│   ├── home/                     # Tab 0 - 首页 (feed)
│   ├── booking/                  # Tab 1 - 订场
│   ├── publish/                  # Tab 2 "+" 弹出后的页面
│   ├── chat/                     # Tab 3 - 消息
│   ├── profile/                  # Tab 4 - 我的
│   └── common/                   # 公共页面
├── components/                   # 公共组件
└── utils/                        # 工具函数
    ├── request.js                # HTTP 封装
    ├── auth.js                   # 登录流程
    ├── wxpay.js                  # 微信支付封装
    ├── permission.js             # 权限判断
    └── upload.js                 # 图片上传
```

## 6. 部署架构

```
                    ┌─────────────┐
                    │   用户微信   │
                    └──────┬──────┘
                           │ HTTPS
                    ┌──────▼──────┐
                    │  Nginx:443  │  (SSL 终端 + 反向代理)
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
     ┌────────▼───┐ ┌─────▼─────┐ ┌───▼────────┐
     │  fastapi_1  │ │ fastapi_2 │ │  静态资源   │
     │  :8000      │ │ :8000     │ │  (OSS)    │
     └──────┬──────┘ └─────┬─────┘ └────────────┘
            │              │
            └──────┬───────┘
                   │
        ┌──────────┼──────────┐
        │          │          │
  ┌─────▼─────┐ ┌──▼────┐ ┌──▼──────┐
  │   MySQL   │ │ Redis │ │  Celery  │
  │   :3306   │ │ :6379 │ │  Worker  │
  └───────────┘ └───────┘ └─────────┘
```

### Docker Compose 结构

```yaml
services:
  nginx:
    image: nginx:alpine
    ports: ["80:80", "443:443"]
  api:
    build: ./backend
    depends_on: [mysql, redis]
  mysql:
    image: mysql:8.0
  redis:
    image: redis:7-alpine
  celery_worker:
    build: ./backend
    command: celery -A app.tasks worker
```

## 7. 关键风险

- **微信分账限制**：分账比例上限 30%，支付后锁定 30 天才能发起
- **场地并发锁**：必须 Redis SET NX + DB 唯一约束双重保障，Celery 定时任务兜底释放过期锁
- **小程序审核**：涉及 UGC（约球帖）需接入微信内容安全 API
- **支付证书管理**：微信商户号 APIv3 证书有有效期，需定时更新并告警
- **图片合规**：用户上传头像、俱乐部封面图需要接入图片安全审核

## 8. 验证方案

- **并发预约**：JMeter/Locust 模拟 100 用户同时预约同一时间段，确认仅 1 个成功
- **支付幂等**：重复发送微信支付回调，确认订单状态不重复更新
- **锁超时释放**：创建预订单不支付，10min 后验证场地自动解锁 + Celery 兜底
- **分账全链路**：支付 → 等待 30 天 → 分账 → 到账（可用微信沙箱环境提前验证）
- **小程序 E2E**：登录 → 选场 → 支付 → 发约球帖 → 他人报名 → 审核
- **权限兜底**：普通用户直接调用管理接口，确认后端返回 403

## 9. Phase 1 实现记录（2026-06-14）

### 9.1 Venue 模型扩展
- 新增 `open_time`（默认 08:00）和 `close_time`（默认 22:00）字段
- `sport_type` 默认值改为 `"tennis"`
- 前端去除全部运动类型选择，固定为网球

### 9.2 时段切分规则
- 创建场地时自动按营业时间以 **30 分钟** 间隔生成未来 **3 天** 全部时段
- 使用 `db.add_all()` 批量插入优化性能（84 条 INSERT → 1 条）
- 30 分钟时段价格 = 小时价 / 2
- 查询时段时自动检测 Redis 锁 TTL，过期锁自动释放 DB 状态

### 9.3 预约规则
- 最小预约单位 = **1 小时**（连续 2 个 30 分钟时段）
- 前端点击一个 slot 自动选中当前 + 下一个 = 1 小时，黄色高亮
- 已约 = 灰色，锁定中 = 浅灰
- `POST /bookings` 支持 `slot2_id` 参数同时锁定两个时段
- Redis SET NX EX 10 分钟锁 + DB 状态双重保障

### 9.4 支付占位
- `POST /bookings/{id}/pay` 当前直接标记订单为已支付
- 支付成功同步释放 Redis 锁 + 标记 slot 为 booked + 创建分账记录 + 通知
- 微信 JSAPI V3 接入待后续完成

### 9.5 约球帖双模式
- **自由约球**：不关联场地，仅发布约球信息
- **订场约球**：内嵌时段选择器 → 用户选取 1 小时 → 自动创建预约并支付 → 关联场地和预约 ID
- 首页帖子卡片：自由约球 = 绿色标签，订场约球 = 黄色标签

### 9.6 预发布检查
- `scripts/preflight.sh`：语法编译 + 15 个模块导入检查
- 后端请求日志中间件：记录方法/路径/状态码/耗时/请求体
- `backend/tests/smoke_test.py`：健康检查 + 俱乐部 + 场地 + 时段 + 帖子接口

### 9.7 日志
- 双通道日志（控制台 + `backend/app.log` 文件）
- 请求日志包含请求体（POST/PUT/PATCH，限 2000 字符）
