# 前后端与数据库审核及修复（2026-10-09）

依据当前工作区代码完成审核，并按确认后的规则修复。退款/分账 SDK 暂缓；报名留言保持公开；订场为今天起三天，可以在营业时间外发起预约，目标时段仍须处于俱乐部营业时间内。新接口不保留旧客户端兼容分支。

工作区原有文档删除保持原样。业务修复先在本地和隔离数据库验证。用户随后明确授权正式认证材料迁移：已只读核对正式资料、创建私有桶、更新桶配置并收紧旧 COS 认证目录权限；已用正式备份恢复副本验证结构升级。后端发布正在推进，小程序尚未上传；没有轮换正式密钥。

## 已修改的位置

| 范围 | 位置 | 结果 |
| --- | --- | --- |
| 预约占用安全（R1） | `backend/app/api/v1/bookings.py`、`services/booking_locks.py`、`services/payment_callback.py`、`tasks/tasks.py` | 时段记录订单归属；Redis 使用订单编号作为锁值，释放时比较锁值。支付校验时效、完整时段及归属；取消、关闭/退款回调和过期任务只能释放自己的时段。订单及相关时段读取加锁。真实迟到收款仍记录异常通知，不自动接入退款。 |
| 排期并发和边界（R3） | `backend/app/services/slots.py`、`api/v1/clubs.py`、`api/v1/venues.py`、`tasks/tasks.py` | 公共订场限今天起三天；补齐营业时间内的 30 分钟时段，保留有效旧排期并跳过重叠区间。生成及订场统一先锁场地，再锁订单/时段；修复真实 MySQL 并发测试发现的死锁。查询及创建前安全回收过期订单。 |
| 价格规则（R4） | `backend/app/schemas/schemas.py`、`services/pricing.py`、`api/v1/venues.py` | 拒绝负价、非有限数、超出金额精度/上限、非法日期与时段；零价规则允许。保留原有规则优先于人工覆盖价的次序；时段报价与订单共用按时长计价及分精度舍入。新增订单保存逐时段价格快照。 |
| 个人资料（R5） | `backend/app/services/public_identity.py`、`core/public_identity.py`、`schemas/schemas.py`、`api/v1/posts.py`、`services/privacy.py` | API 输出独立公开用户编号，包括赛事字典响应和个人资料编号，公开内容不返回内部 OpenID；无昵称使用普通兜底名称。完整发起人手机号仅本人、已通过报名者及平台管理员可见；报名留言继续公开。 |
| 认证材料（R5） | `backend/app/main.py`、`services/storage.py`、`services/privacy.py`、`api/v1/clubs.py` | 俱乐部材料仅申请人、所属管理员及平台管理员可见。新材料必须由本人经私有上传生成；支持最大 10 MB 的 PDF/图片，PDF 校验文件头。使用独立私有 COS 桶或独立本地私有目录，经鉴权下载；本地旧 `/uploads/doc/` 不再由应用静态服务提供。已授权正式迁移并收紧旧公开目录；实际检查该目录当前对象和历史版本均为零。 |
| 异步任务（R6） | `backend/app/tasks/runtime.py`、`tasks/tasks.py`、`core/redis.py`、`services/tournament_maintenance.py` | 每次同步任务单独创建 NullPool 数据库资源与 Redis 客户端，通过 ContextVar 传递；成功/异常均关闭，不复用上一事件循环的连接。 |
| 数据库一致性（R7） | `backend/app/models/models.py`、`alembic/review_integrity.py`、`alembic/versions/20261009_review_integrity.py` | 新增 `booking_slots`、时段订单归属、公开编号及私有上传记录；分账订单唯一约束、签表组合外键和恢复查询索引。迁移在任何 DDL 前检查异常引用、重叠时段、价格、重复分账、跨签表及无法确定的占用归属，输出表名/记录编号后拒绝执行。 |
| 约球状态与历史（R8） | `backend/app/api/v1/posts.py` | 名额不可低于已通过人数；满员由服务端计算；关闭不可重开。移除旧硬删除接口，仅通过 `/close` 关闭，保留报名及评论。兼容枚举对象/字符串。 |
| JWT（R9） | `backend/app/core/config.py`、`backend/.env.example`、`.github/workflows/deploy.yml`、`scripts/validate-production.py` | DEBUG=false 时拒绝缺失、公开示例/默认值或少于 32 字符的密钥；发布预检提前拒绝。保留已有合格密钥，无密钥轮换；CI 使用隔离测试值。 |
| 恢复与列表性能（R10） | `backend/app/services/tournament_maintenance.py`、`tasks/tasks.py`、`api/v1/posts.py` | 恢复查询按最后尝试时间和编号排序，失败也记录尝试以轮转后续批次；过期任务不再每个时段重扫全部订单；等级筛选只读取去重等级值；评论回复及数量批量查询，移除逐条查询。 |
| 发布持久化 | `compose.production.yml`、`scripts/prepare-production.py`、`scripts/deploy-production.py` | 为本地私有材料增加独立持久化目录、受限目录权限及备份覆盖；旧公开认证文件不再作为公开图片健康检查样本。仅改本地发布代码。 |
| 前端接口 | `frontend/src/pages/booking/confirm.vue`、`pages/publish/slot-manage.vue` | 仅发送 `slot_ids`，至少两个连续时段；排期只提供 30 分钟选项，订单过期可重新提交。后端另校验至少一小时，旧单 `slot_id` 请求不再支持。 |
| 前端稳定性（前轮修复） | `frontend/src/services/api.ts`、`stores/session.ts`、`utils/date.ts`、`pages/home/index.vue`、`pages/booking/venue-detail.vue`、`pages/profile/my-bookings.vue`、`pages/publish/post-create.vue` | 保留共享刷新机制，账号切换使旧请求失效；登录回跳保留参数；统一上海业务日期；忽略旧请求结果；预约与首页列表正确分页，并补加载失败提示。 |
| 其他前轮修复 | `backend/app/main.py`、`core/database.py`、`schemas/schemas.py`、`api/v1/clubs.py` | 有界读取上传；SQL 参数隐藏；资料及编辑字段校验；上海日期下的 UTC 订单统计边界。 |

## 迁移及新接口的边界

- Alembic 唯一 head：`20261009_review_integrity`。应用和 Worker 必须在迁移完成后使用新代码；前端需同步发布新预约接口。此轮没有执行发布。
- 数据库保留历史 `slot_id` / JSON `slot_ids`，作为历史数据与稽核来源；新支付/释放从外键明细读取。这是历史数据保留，不是旧创建接口兼容。
- 历史订单的原金额保留；无法可靠恢复的逐时段历史价格记为 NULL，未按当前价格伪造历史快照。
- 正式迁移需现有备份、停写、恢复副本演练及数据预检。发现历史异常会在 DDL 前停止，需先决定修复数据；MySQL DDL 失败遵循备份恢复边界，不自动降级。
- 存量 Redis 用户标识锁不会被新订单锁误删，最长等待既有 TTL；正式切换应在停写窗口确认旧 pending 订单和锁的状态。

## 未修改/待正式操作的风险

1. **退款/分账 SDK 与真实资金链路（R2）**：按要求暂缓。SDK 调用和返回值适配未改，真实预订收款/取消退款仍为既有暂缓范围；不能把占位 `paid` 视为真实收款。回调仅修复占用归属和幂等安全，不代表真实退款/分账已验收。
2. **旧 COS 认证材料直链（R5 的存量部分）**：接口隐藏不能撤销已知公网 URL。新材料要求 `COS_PRIVATE_BUCKET_NAME` 为同区域的独立私有桶，且禁用匿名读取；未配置时 COS 模式下的认证材料上传会拒绝。旧 COS 文件、旧数据库链接和可能存在的 Nginx 静态访问仍需正式环境迁移和权限收紧。2026-10-09 已创建 `tennis-miniapp-private-1300427458`，仅授应用子账号认证目录 PutObject/GetObject；应用上传/读取成功，匿名读取 403。旧公有桶 doc 目录匿名当前及版本读取均拒绝，其他目录公读正常；实测无存量认证对象、历史版本或数据库资料链接。
3. **正式副本验证已补齐**：已恢复当前正式数据库备份并完成 head 升级、重复升级及原字段全表数据哈希核对。现有正式库已有 Alembic 记录，无版本记录的历史接管套件仍跳过；该路径不用于本次发布。

### 旧认证材料迁移方案（用户已确认，正式执行中）

1. 正式备份并核对所有 `clubs.documents` 对象、申请人和所属管理员，识别无法确定归属或非受控来源的材料，输出受保护清单，不自动处理不明文件。
2. 在同区域配置独立私有桶，确认匿名 GET 被拒绝，给应用密钥最小上传/读取权限；或明确采用持久化本地私有目录。
3. 复制并校验文件哈希，创建私有上传记录，把历史资料地址改为 `/api/v1/media/doc/{filename}`；检查本人、管理员可读、普通用户及匿名访问被拒绝。
4. 验收后撤销旧 `doc/` 对象的匿名读权限，并检查桶策略、版本访问和 Nginx 旧静态路径。**撤权会使历史公读直链失效，需单独确认。**
5. 撤权前可回滚数据库链接；撤权后回滚须继续保持资料私有，不能自动恢复匿名读取。正式数据库迁移、后端部署和小程序发布分别执行，不在本轮顺带上线。

## 验证记录

使用 Python 3.12、Node 20、隔离 MySQL 8.4 和 Redis；所有测试连接显式使用本机临时端口与测试数据库。没有读取或输出正式密钥。

- 后端全量测试：259 passed、3 skipped、10 deselected。3 项跳过为完整迁移恢复套件；其中空库重复升级另行执行并通过（1 passed），正式备份接管/异常恢复两个场景尚未演练。10 项为明确暂缓的预约真实支付/退款测试，未删除或弱化断言。
- 迁移：隔离空库完整升级和重复升级、旧结构历史订单保留、非法引用/负价格/重叠时段/重复分账/跨签表在 DDL 前拒绝，以及真实组合外键拒绝非法引用均通过。
- 并发：真实 MySQL/Redis 下同一时段竞争、同时补排期、订场与补排期并发、旧订单过期后重订通过。
- 任务：真实数据库/Redis 下连续成功、失败、再次成功的任务使用不同事件循环且资源关闭；恢复首批 100 条持续失败时下一批仍可处理。
- 前端 `npm run check:miniprogram`：类型检查、69 项测试、生产小程序构建和上传 dry-run 通过；未上传。Wot UI 查询 2.3.2 MCP API，用法检查无错误，保留 7 条已有子组件元数据警告。
- 部署脚本：15 项测试通过；Python 编译及新增文件 Ruff 检查通过。
- 未做真实 WeChat 登录/支付/退款/分账、真实 Celery Worker 进程重启、真机验收及大规模压测。

## 正式执行进度（2026-10-09）

- 用户已明确授权直接迁移正式认证材料。tccli OAuth 凭据经自动续期验证；没有把临时管理凭据写入应用。
- 正式备份及恢复副本：`/var/backups/playnow/20261009T025644Z-review-rehearsal`，原 23 张表既有字段数据哈希保持一致，副本升级到 `20261009_review_integrity` 并重复升级成功。临时数据库/账号已删除。
- 新增 `backend/scripts/migrate_private_documents.py`：受控来源和归属预检、受保护备份、SHA256 校验、资料地址事务更新；并发变化拒绝，不自行撤销权限。新增 8 项测试通过。
- HTTP 90 项业务流程通过，包括公开用户编号审核、三天/30 分钟预约及关闭后保留报名历史。
- 私有 COS 桶、最小目录权限、旧 doc 匿名访问撤销和当前/历史版本探针已验证；探针已清理。正式 API/Worker 发布和最终资料迁移命令待流水线完成后验收。
