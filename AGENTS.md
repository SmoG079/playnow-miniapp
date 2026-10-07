# PlayNow 项目协作指南

本文面向在本仓库工作的编码 Agent，替代原 `CLAUDE.md`。审核基准为 2026-10-07 的项目文档及当前工作区代码；具体依赖、命令和行为以对应配置及实现为准。

## 文档使用原则

- 先读任务相关文档，再核对当前实现与测试。需求规范描述目标，实施记录和验收报告描述特定版本的结果，不能据此推断当前分支或线上环境已具备全部功能。
- 根目录 `README.md` 仍含已删除的 `miniprogram/`、旧分支和旧接口说明；`docs/wot-toolchain.md` 中“尚未安装 UI 运行时”也已过时。不要按这些历史内容恢复旧架构。
- 自由约球权限参考 [2026-09-04 修复记录](docs/frontend-fixes-2026-09-04.md) 及当前接口；早期 [发布规范](docs/post-create-spec.md) 中“所有约球帖仅管理员可发”的要求已不适用于自由约球。
- 部署文档中的“待执行”“已完成”有时间和版本边界；操作前核对目标版本及实际状态。不要把另一个工作区或提交的验收结果当作本分支的验证结果。

## 项目结构与技术栈

PlayNow 是面向网球俱乐部的微信小程序，提供场地预约、约球社交和比赛报名。当前产品聚焦网球。

| 路径 | 用途 |
| --- | --- |
| `frontend/` | 唯一前端：uni-app、Vue 3、TypeScript、Pinia、Wot UI v2，主要构建目标为 `mp-weixin` |
| `backend/app/` | FastAPI API、SQLAlchemy 异步模型、业务服务和 Celery 任务 |
| `backend/alembic/` | 数据库迁移与固定结构快照 |
| `backend/tests/` | 后端业务与迁移测试 |
| `scripts/`、`tests/` | 部署、上传脚本及部署流程测试 |
| `.github/workflows/deploy.yml` | 检查、后端发布和可选小程序体验版上传 |
| `docs/` | 需求、实现记录、运维文档和验收记录 |

- 原生 `miniprogram/` 已删除，不再作为开发或上传入口。
- 前端依赖及版本以 `frontend/package.json` 和锁文件为准；当前 Wot UI 包为 `@wot-ui/ui` 2.3.2。根目录依赖用于 Wot CLI 和小程序上传，两处依赖需分别安装。
- 后端 Docker 和 CI 使用 Python 3.12，配套 FastAPI、SQLAlchemy 2.x、MySQL 8、Redis 7、Celery。Node.js 使用与 CI 一致的 20。
- 不在指南中维护“当前工作分支”、固定页面数或历史包体积；分别检查 Git、`frontend/src/pages.json` 和本次构建产物。

## 前端约定

- 路由和原生 tabBar 在 `frontend/src/pages.json`。保留首页、订场、发布、消息、我的五个入口及 `frontend/src/static/tabbar/` 图标；不要无故改为 custom tabBar。
- 全局使用自定义导航栏。复用 `frontend/src/components/AppShell.vue`，处理状态栏与安全区；新增页面同时维护路由，增加页面较多时评估分包和实际包体积。
- Wot UI 的 easycom 规则指向 `@wot-ui/ui/components/`，组件无需逐个手动导入。相关 hook 从已安装的 `@wot-ui/ui` 包导入，不照搬 `uni_modules` 路径。
- **生成或修改 Wot UI 组件代码前，必须阅读 `.agents/skills/wot-ui-v2/SKILL.md`，并查询项目配置的 `wot-ui` MCP 服务获取版本匹配的 API 和示例。** CLI 查询可辅助排查，但不能省略项目要求的 MCP 查询。服务不可用时明确说明限制，不凭记忆猜测 API。
- `useToast`、`useDialog`、`useNotify` 的调用需配套页面中的组件实例；具体用法按 Skill 和 MCP 查询结果执行。
- 请求和上传统一经 `frontend/src/services/api.ts`，保留 Bearer Token、401 刷新与并发共享的 `refreshPromise` 机制。
- 会话与角色状态使用 `frontend/src/stores/session.ts`。角色包括 `user`、`club_admin`、`platform_admin`；前端入口控制不能替代后端鉴权。
- API 地址在 `frontend/src/config.ts`，当前指向线上 `https://www.tennisplaynow.site:8443/api/v1`。本地写入联调前应切换到隔离后端，避免误操作线上数据；不要将临时地址提交为发布配置。
- 微信开发者工具导入构建目录。发布前按实际请求、上传和下载链路核对公众平台合法域名配置，开发工具关闭域名校验不代表真机验收通过。

## 后端与业务约定

- 入口为 `backend/app/main.py`，API 前缀默认 `/api/v1`；模型、请求响应定义分别在 `backend/app/models/models.py` 和 `backend/app/schemas/schemas.py`。
- 数据库结构由 Alembic 管理，应用启动不执行 `Base.metadata.create_all`。修改模型时同步考虑迁移和兼容性，不能仅修改 ORM 就声称数据库已升级。
- 数据库驱动为 `asyncmy`。处理枚举时复用现有 `_v()` 兼容枚举对象和字符串；读取时间字段时核对实际类型，不假定原始驱动值与 ORM 返回值完全一致。
- 鉴权依赖位于 `backend/app/api/deps.py`。管理操作应核对角色和具体俱乐部归属，不能仅凭前端的 `isClubAdmin` 放行。平台管理员是否豁免归属校验需核对对应接口，不能假定所有接口行为一致。
- 登录流程为 `uni.login()` → `/auth/login` → access/refresh token。当前工作区的登录及手机号接口仍有 `dev_` 旁路，且未加环境开关；只用于隔离开发测试，不得把它描述为已在生产自动禁用。

### 场地与预约

- 营业时间来自 `Club.opening_time` / `Club.closing_time`。创建场地会生成从当天起三天的 30 分钟时段；俱乐部时段查询还可能补齐缺失排期，因此相关 GET 不能一概视为无写入。
- 产品及前端要求至少两个连续的 30 分钟时段（1 小时起订）；当前后端创建接口仍兼容单个 `slot_id`，不要宣称服务端已强制 1 小时起订。
- 多时段订单必须考虑同一场地、同一日期、连续性、可用状态和已过期时间。保留数据库行锁及 Redis 锁协作，锁键为 `slot:{venue_id}:{date}:{start_time}`，默认 TTL 为 600 秒，由配置控制。
- 修改预约、取消或锁释放时同时核对 `slot_id` 与 `slot_ids` 的兼容行为，不能只处理首个时段。列表对过期 Redis 锁的清理不等于支付路径已完成过期校验。
- `Venue.price_rules` 包含 `date_range` / `daily_time` 规则；时段还可能有 `price_override`。修改价格时同时核对展示报价、生成排期和订单金额；当前各路径规则并不完全统一，不能以客户端金额作为服务端结算依据。
- 业务日期和时段使用 `Asia/Shanghai`；订单内部时间戳按现有 UTC-naive 约定处理，比较前显式统一时区。

### 约球与比赛

- 自由约球无需俱乐部，普通登录用户可发布。关联俱乐部的约球帖走管理员及成员关系校验；前端关联场地流程还要求先完成订场。
- 订场回传使用 `uni` Storage 的 `booking_return`，发布页读取后删除，不使用旧原生小程序的 `globalData`。
- 比赛创建和场地管理按具体俱乐部权限校验。订场和约球报名页面包含手机号检查，不应推断所有报名接口都有服务端手机号校验。

### 支付、退款与分账边界

以 [预订支付与退款待办](docs/deferred-booking-payments.md) 为当前范围约束：

- 预订 `/bookings/{id}/pay` 仍是占位实现，直接标记 `paid` 并生成 `dev_` 交易号，不代表真实收款。
- `/bookings/{id}/cancel` 取消订单并释放时段，不按距开始时间计算退款，也不调用真实微信退款。
- 微信支付、管理员退款、回调和分账相关代码存在，不代表真实资金链路已经验收；赛事报名支付也需单独核验。
- 真实预订支付和取消退款规则已明确暂缓。除任务要求恢复这部分功能外，不在无关改动中顺带接入或重写，也不将旧支付规范中的目标描述成当前行为。
- CI 排除标记为 `deferred_booking_payments` 的 10 项历史测试。保留测试及待办说明，不通过删除断言或掩盖失败声称全部测试通过；不带排除条件运行时仍会执行这些测试。

## 媒体存储与日志

- 新上传经后端 `/api/v1/upload`，存储实现位于 `backend/app/services/storage.py`；前端复用 `uploadFile()` 和 `Photo.vue`。生产预期使用腾讯云 COS，配置与边界见 [COS 文档](docs/cos-media-storage.md)。当前工作区实现已支持 COS 配置缺失时回退本地磁盘；与文档有差异时核对代码及部署版本，不能据此断言线上已切换。
- `file_type` 支持 `avatar`、`court`、`post`、`video`、`doc`，其它值回落 `upload`。前缀存在不代表接口支持该文件类型：当前默认仅接受 jpg/jpeg/png/webp/gif，大小上限 5 MB，尚未开放 PDF 或视频上传。
- `/uploads` 静态挂载兼容旧链接，并服务本地存储回退路径；移除前需完成文件与链接迁移，确认不再依赖本地存储。
- COS 使用 `OSS_*` 配置和最小权限子账号密钥。当前桶公有读，`doc/` 认证材料也未实现私有访问；不能把目录前缀当作权限隔离。
- 日志复用 `backend/app/core/logger.py` 的 `get_logger(__name__)`。调试值用 `debug`，关键状态变更用 `info`，异常用 `error(..., exc_info=True)`；不记录 Token、密钥或完整敏感资料。
- 日志级别、目录和轮转由 `backend/app/core/config.py` 的 `LOG_*` 配置控制；保留请求日志中间件与独立 SQL 日志设置。

## 开发与验证

以下命令均标注工作目录；按改动范围执行检查，并在交付时说明实际运行结果与未验证项。

### 前端（仓库根目录）

```bash
npm ci
npm ci --prefix frontend
npm run dev:mp-weixin --prefix frontend
# 或 H5 预览：http://127.0.0.1:5188
npm run dev:h5 --prefix frontend
```

开发小程序产物位于 `frontend/dist/dev/mp-weixin`。前端代码改动执行类型检查和相关测试，Wot UI 改动另跑用法检查：

```bash
npm run typecheck --prefix frontend
npm test --prefix frontend
npm run wot:lint --prefix frontend
```

完整小程序发布前检查与 CI 对齐：

```bash
npm run check:miniprogram
```

该命令包含类型检查、前端测试、生产构建和上传 dry-run；产物位于 `frontend/dist/build/mp-weixin`，不会实际上传。

### 后端（`backend/` 目录）

使用 Python 3.12 虚拟环境。先将 `DATABASE_URL`、`REDIS_URL` 和 JWT 配置显式指向隔离开发环境；不要直接使用配置文件中指向远程主机的默认连接。

```bash
python -m pip install -r requirements.txt pytest pytest-asyncio
# 仅适用于空库或已有 Alembic 版本记录的开发库
python -m alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

与当前 CI 对齐的后端检查：

```bash
python -m compileall app alembic scripts -q
python -m unittest tests/test_free_post_queries.py
python -m pytest tests/test_rate_limit.py tests/test_bookings.py tests/test_settlement.py -m "not deferred_booking_payments"
```

部署脚本改动在仓库根目录执行：

```bash
python -m unittest discover -s tests -p 'test_deployment*.py' -v
```

迁移改动还需验证隔离空库升级、重复升级及受影响的已有结构。恢复副本演练使用 `backend/tests/test_migration_integration.py`，环境和数据库命名要求见 [数据库迁移操作文档](docs/database-migration-runbook.md)；环境缺失导致跳过不算通过。旧 `scripts/preflight.sh` 和 `backend/tests/smoke_test.py` 已不存在，不再使用。

## 迁移与发布

- 详细流程参考 [CI/CD 文档](docs/cicd-wechat-miniprogram.md)、[数据库迁移操作文档](docs/database-migration-runbook.md) 和 [正式 Compose 文档](docs/production-compose-runbook.md)，执行入口以当前工作流及脚本为准。
- PR 到 `master` 执行检查；push 到 `master` 在检查通过后自动部署后端。推送前应理解该发布副作用，检查通过不能表述为已完成线上发布。
- 正式环境独立使用 `compose.production.yml`，不要与旧 Compose 文件叠加。API 绑定宿主机 `127.0.0.1:8000`，HTTPS 由宿主机 Nginx 提供；保留既有外部数据卷及持久化挂载。
- 镜像以完整提交 SHA 固定。发布是单机停写维护流程，由 `scripts/remote-deploy.py` 和 `scripts/deploy-production.py` 处理传输、备份、迁移与验收，不保证零停机。
- 无 Alembic 记录的历史库走显式接管流程，不能直接 `stamp head` 或盲目 `upgrade head`；先只读预检，完成备份、恢复演练及停写后再应用。已有版本记录的库走正常迁移。
- 结构变更失败不能依赖 MySQL DDL 事务回滚，也不能盲目降级或切回旧镜像；遵循脚本和迁移文档的失败恢复边界。
- 小程序上传默认关闭；体验版上传、真机验收、微信审核及正式发布是独立环节，不因后端部署完成而自动视为完成。
- 环境文件、私钥、数据库备份和含凭据的 Compose 展开结果不得提交或输出到聊天、CI 日志与公开产物中。
