# PlayNow 运动俱乐部小程序

面向运动俱乐部（羽毛球、篮球、网球等）的微信小程序 SaaS 平台。俱乐部可发布场地信息和时间表，用户在线预约并微信支付，平台通过微信分账 API 与俱乐部结算。同时提供约球社交和比赛报名功能。

## 技术栈

| 层面 | 技术 |
|------|------|
| 小程序前端 | 原生微信小程序 (WXML/WXSS/JS) |
| 后端 API | Python FastAPI + Gunicorn + Uvicorn |
| 数据库 | MySQL 8.0 |
| 缓存/锁 | Redis 7 |
| 对象存储 | 阿里云 OSS / 腾讯云 COS |
| 任务队列 | Celery (释放过期锁、分账重试) |
| 部署 | Docker Compose + Nginx |
| 支付 | 微信支付 V3 API + 分账 |

## 项目结构

```
playnow-miniapp/
├── miniprogram/           # 微信小程序前端
│   ├── app.js             # 全局配置、请求拦截、角色管理
│   ├── app.json           # 路由 + 自定义 TabBar 配置
│   ├── custom-tab-bar/    # 5 Tab 自定义底部导航（含 "+" 弹窗）
│   ├── pages/
│   │   ├── home/          # 首页 - 约球帖 feed + 比赛推荐
│   │   ├── booking/       # 订场 - 俱乐部列表、场地时间表、预约支付
│   │   ├── publish/       # 发布 - 约球帖/俱乐部/比赛/管理（按角色）
│   │   ├── chat/          # 消息 - 群聊列表 + 微信客服
│   │   ├── profile/       # 我的 - 角色化个人/俱乐部管理
│   │   └── common/        # 公共页面 - 登录、详情页
│   └── utils/
│       ├── auth.js        # 微信登录
│       ├── request.js     # HTTP 封装（自动 token 刷新）
│       ├── permission.js  # 角色权限判断
│       └── wxpay.js       # 微信支付封装
│
├── backend/               # Python FastAPI 后端
│   ├── app/
│   │   ├── main.py        # FastAPI 入口
│   │   ├── api/v1/        # RESTful API 路由（7 个模块）
│   │   ├── models/        # SQLAlchemy ORM 模型（12 张表）
│   │   ├── schemas/       # Pydantic 请求/响应模型
│   │   ├── core/          # 配置、数据库、JWT、Redis
│   │   └── tasks/         # Celery 定时任务
│   ├── nginx/             # Nginx 反向代理配置
│   ├── Dockerfile
│   └── requirements.txt
│
├── docker-compose.yml     # 一键启动全部服务
└── .gitignore
```

## 快速开始

### 前置条件

- Docker & Docker Compose
- 微信小程序 AppID + AppSecret（[微信公众平台](https://mp.weixin.qq.com) 获取）
- 微信商户号（[微信支付商户平台](https://pay.weixin.qq.com) 申请）
- 域名 + SSL 证书（用于 API 和微信支付回调）

### 1. 配置环境变量

```bash
cd backend
cp .env.example .env
```

编辑 `.env`，填入实际的微信和数据库配置：

```ini
# 必填项
WX_APP_ID=你的小程序AppID
WX_APP_SECRET=你的小程序AppSecret
WX_MCH_ID=你的微信商户号
WX_MCH_API_V3_KEY=商户APIv3密钥
WX_MCH_SERIAL_NO=证书序列号
WX_PAY_NOTIFY_URL=https://api.你的域名.com/api/v1/bookings/wx-notify

# 数据库（如修改需同步 docker-compose.yml）
DATABASE_URL=mysql+aiomysql://club_user:club_pass@mysql:3306/club_db

# JWT（生产环境务必修改）
JWT_SECRET_KEY=生成一个随机字符串至少32位
```

### 2. 配置 SSL 证书

```bash
mkdir -p backend/ssl
# 将你的 SSL 证书放入 backend/ssl/
# fullchain.pem  - 完整证书链
# privkey.pem    - 私钥
```

如无正式证书，可先用 Let's Encrypt 申请免费证书。

### 3. 配置微信支付证书

```bash
mkdir -p backend/certs
# 将微信商户平台下载的 apiclient_key.pem 放入 backend/certs/
```

### 4. 启动服务

```bash
# 在项目根目录执行
docker-compose up -d

# 查看启动状态
docker-compose ps

# 查看日志
docker-compose logs -f api
```

启动后访问：
- API 文档: `https://api.你的域名.com/docs`
- 健康检查: `https://api.你的域名.com/health`

### 5. 配置微信小程序

1. 用 [微信开发者工具](https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html) 打开 `miniprogram/` 目录
2. 修改 `miniprogram/project.config.json` 中的 `appid` 为你的 AppID
3. 修改 `miniprogram/app.js` 中 `baseURL` 为你的 API 地址
4. 在微信公众平台配置服务器域名白名单（request 合法域名）

### 6. 数据库迁移（生产环境）

开发阶段使用 SQLAlchemy auto-create。生产环境推荐使用 Alembic：

```bash
# 进入 api 容器
docker-compose exec api bash

# 初始化 Alembic（首次）
alembic init alembic

# 生成迁移脚本
alembic revision --autogenerate -m "init"

# 执行迁移
alembic upgrade head
```

## 角色权限

| 角色 | 说明 | 权限 |
|------|------|------|
| `user` | 普通用户 | 预约场地、发布约球帖、报名比赛 |
| `club_admin` | 俱乐部管理员 | user 权限 + 管理俱乐部和场地、创建比赛、查看订单和分账 |
| `platform_admin` | 平台超管 | 全部权限 |

用户创建俱乐部后自动成为 `club_admin`。权限前端 UI 控制 + 后端 API 双重校验。

## API 概览

```
Base URL: https://api.你的域名.com/api/v1

认证:   POST /auth/login          # 微信登录
用户:   GET  /users/me            # 个人信息
俱乐部: GET  /clubs               # 俱乐部列表
       POST  /clubs               # 创建俱乐部
场地:   GET  /venues/:id/slots    # 查看时间段
预约:   POST /bookings            # 创建预约（锁场）
       POST /bookings/:id/pay     # 发起支付
       POST /bookings/wx-notify   # 微信支付回调
约球:   GET  /posts               # 约球帖列表
       POST /posts               # 发布约球帖
比赛:   GET  /tournaments         # 比赛列表
       POST /tournaments          # 创建比赛 [club_admin]
```

完整 API 文档启动后访问 `/docs` 查看 Swagger UI。

## 核心业务流程

### 预约 & 支付

```
选场地 → 选时间段 → 下单锁场(Redis 10min) → 微信支付 →
支付回调 → 更新订单 → 生成分账记录 → 30天后微信分账API分账
```

### 场地锁机制

- **Redis 锁**: `SET slot:{venue}:{date}:{start} user_id NX EX 600`
- **DB 状态**: `venue_time_slots.status = 'locked'`
- **兜底释放**: Celery 每 60s 扫描过期锁自动释放

### 分账模型

```
用户支付 100元 → 平台商户号 →
30天后微信分账API → 平台 10元(抽10%) + 俱乐部 90元(分账)
```

## 常见问题

**Q: 微信分账比例上限？**
A: 默认 30%。如需更高比例需向微信商务特殊申请。

**Q: 分账什么时候可以发起？**
A: 用户支付成功后锁定 30 天，30 天后可调用微信分账 API。

**Q: 如何添加新的运动类型？**
A: 修改 `backend/app/models/models.py` 中场地和比赛的 `sport_type` 字段注释即可，无需改表结构。

**Q: 小程序审核需要注意什么？**
A: UGC 内容（约球帖）需接入微信内容安全 API；比赛报名费可能涉及虚拟支付审核分类。

## License

MIT
