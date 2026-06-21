# 网球俱乐部小程序

面向网球俱乐部的微信小程序平台。俱乐部发布场地信息，用户在线预约，同时提供约球广场社交和比赛报名功能。

## 技术栈

| 层面 | 技术 |
|------|------|
| 小程序前端 | 原生微信小程序 (WXML/WXSS/JS) |
| 后端 API | Python 3.11 + FastAPI + Uvicorn |
| 数据库 | MySQL 8.0 (asyncmy driver) |
| 缓存/锁 | Redis 7 |
| 部署 | 云服务器 + Docker Compose + Nginx |
| 支付 | 微信支付 V3（占位，待接入） |

## 项目结构

```
├── miniprogram/               # 微信小程序前端
│   ├── app.js                 # 全局配置、请求拦截、Token 管理
│   ├── app.json               # 路由 + TabBar 配置
│   ├── custom-tab-bar/        # 5 Tab 自定义底部导航（含 "+" 弹窗）
│   ├── pages/
│   │   ├── home/              # 首页 - 约球广场 + 比赛（NTRP/日期/距离筛选）
│   │   ├── booking/           # 订场（3天网格、30min切分、1h起订）
│   │   ├── publish/           # 发布中心（约球帖/比赛/俱乐部/场地管理）
│   │   ├── profile/           # 我的（预约/活动管理/俱乐部管理）
│   │   ├── common/            # 公共页面（登录/详情/编辑资料）
│   │   └── admin/             # 管理页面（订单/场地/俱乐部）
│   └── utils/
│       ├── auth.js            # 微信登录 + 手机号 + 登录态检查
│       ├── permission.js      # 角色权限判断
│       └── wxpay.js           # 支付封装
│
├── backend/                   # Python FastAPI 后端
│   ├── app/
│   │   ├── main.py            # 入口 + 图片上传
│   │   ├── api/v1/            # 7 个模块（auth/users/clubs/venues/bookings/posts/tournaments）
│   │   ├── models/            # 15 张表
│   │   ├── schemas/           # Pydantic 模型
│   │   ├── core/              # 配置/数据库/JWT/Redis/限流/微信支付
│   │   ├── services/          # 支付回调/分账服务
│   │   └── tasks/             # Celery 定时任务
│   ├── alembic/               # DB 迁移
│   ├── tests/                 # API 冒烟测试
│   ├── Dockerfile
│   └── requirements.txt
│
├── scripts/                   # preflight.sh 检查脚本
├── docs/                      # 需求/开发/接口/TODO 文档
└── docker-compose.yml
```

## 本地开发

### 后端

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# API 文档: http://127.0.0.1:8000/docs
```

### 日志系统

后端通过 `app/core/logger.py` 提供统一日志，支持三级分类输出。

**使用方式：**
```python
from app.core.logger import get_logger
logger = get_logger(__name__)

logger.debug("变量值: %s", val)         # DEBUG — 开发调试
logger.info("订单创建: id=%s", oid)     # INFO  — 业务关键节点
logger.error("支付失败", exc_info=True) # ERROR — 异常/错误
```

**日志文件：**
| 文件 | 级别 | 轮转策略 | 保留 |
|------|------|---------|------|
| `logs/debug.log` | 仅 DEBUG | 20 MB | 20 个文件 |
| `logs/info.log` | INFO 及以上 | 每日 0 点 | 10 天 |
| `logs/error.log` | ERROR 及以上 | 每日 0 点 | 10 天 |
| `logs/mysql.log` | SQL 查询（独立） | 20 MB | 20 个文件 |

**配置（`.env`）：**
```env
LOG_LEVEL=DEBUG            # 业务日志级别
LOG_MYSQL_LEVEL=WARNING    # SQL 日志（INFO=显示语句）
LOG_BACKUP_DAYS=10
LOG_MAX_BYTES=20971520     # 20 MB
LOG_BACKUP_COUNT=20
```

### 前端

1. 微信开发者工具打开 `miniprogram/` 目录
2. `app.js` 中 `baseURL` 设为 `http://127.0.0.1:8000/api/v1`
3. 详情→本地设置→勾选「不校验合法域名」

## 角色权限

| 角色 | 获得方式 | 权限 |
|------|---------|------|
| `user` | 默认 | 预约场地、发布约球帖、报名约球/比赛 |
| `club_admin` | 创建俱乐部自动升级 | user 权限 + 管理自有俱乐部（场地/订单/统计）、创建比赛 |
| `platform_admin` | 手动分配 | 全部权限 |

## 功能切分

### Phase 1 已完成（P0）

| 模块 | 功能 | 状态 |
|------|------|------|
| **俱乐部管理** | CRUD、场地管理、仪表盘、营业时间设置 | ✅ |
| **场地管理** | 创建场地自动生成30min时段、特殊价格规则（日期/时段） | ✅ |
| **预约订场** | 3天网格展示、1h起订、锁场10min自动释放、支付占位 | ✅ |
| **约球广场** | 自由约球（无需俱乐部）/ 定场约球（关联场地预约）双模式 | ✅ |
| **比赛系统** | 创建比赛（关联场地）、报名、俱乐部管理员权限 | ✅ |
| **用户系统** | 微信登录、JWT(30天)、角色体系、手机号授权 | ✅ |
| **活动管理** | 约球帖修改/删除、比赛管理 | ✅ |

### 待完成（P1/P2）

| 模块 | 功能 |
|------|------|
| **支付** | 微信支付 V3 真实接入、退款流程 |
| **分账** | 微信分账 API、分账记录管理 |
| **消息** | 订阅消息推送、聊天/群聊 |
| **审核** | 内容安全审核、约球帖报名审核 |

## API 概览

Base URL: `/api/v1`

```
认证:   POST /auth/login       # 微信登录（dev_ 旁路）
        POST /auth/refresh     # 刷新 Token
        POST /auth/phone       # 微信手机号

用户:   GET  /users/me         # 个人信息
        PUT  /users/me         # 更新资料（昵称/头像/手机/NTRP）
        GET  /users/me/bookings # 我的预约
        GET  /users/me/posts    # 我的约球帖
        GET  /users/me/notifications # 通知列表

俱乐部: GET  /clubs             # 列表（支持关键词/LBS/运动类型筛选）
        POST /clubs             # 创建
        GET  /clubs/{id}        # 详情（含场地列表）
        PUT  /clubs/{id}        # 编辑 [club_admin]
        GET  /clubs/{id}/venue-slots?date= # 场地时段网格
        GET  /clubs/{id}/stats  # 统计 [club_admin]

场地:   POST /venues/with-club/{id}   # 创建 [club_admin]
        PUT  /venues/{id}/with-club/{id} # 编辑 [club_admin]
        DELETE /venues/{id}/with-club/{id} # 删除 [club_admin]

预约:   POST /bookings          # 创建（支持多时段 slot_ids）
        POST /bookings/{id}/pay # 支付（占位，直接标记成功）
        POST /bookings/{id}/cancel # 取消
        GET  /bookings/club/{id} # 俱乐部订单 [club_admin]

约球:   GET  /posts             # 列表（NTRP/日期/距离筛选）
        POST /posts             # 创建（自由约球无 club_id 限制）
        PUT  /posts/{id}        # 编辑
        DELETE /posts/{id}      # 删除
        POST /posts/{id}/register # 报名
        DELETE /posts/{id}/register # 取消报名

比赛:   GET  /tournaments       # 列表
        POST /tournaments       # 创建 [club_admin]
        POST /tournaments/{id}/register # 报名

上传:   POST /upload            # 图片上传
```

## 分支说明

| 分支 | 说明 |
|------|------|
| `master` | 主分支（PR #1 已合并） |
| `dev-20260621-1` | 当前开发分支，基于 master |
| `dev-20260621-0` | 第一版开发（合并前） |
| `mix-20260621-0` | 实验性合并分支 |
| `snapshot-2026-06-20` | zg73 的 PR 源分支 |
