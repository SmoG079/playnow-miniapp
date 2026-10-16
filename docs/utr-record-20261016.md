# 我的 UTR 战绩

“我的”新增黑色、青色的 UTR 战绩卡片，仅最新角色确认为 `platform_admin` 后显示。普通用户和俱乐部管理员不显示入口，直接访问页面也不能读取战绩。`GET /api/v1/users/me/utr-record` 独立使用系统管理员鉴权，降权后相同 token 不再有权限。

页面仅一套 UTR 数据，不区分单打、双打。显示 UTR 积分、数据库 NTRP、比赛总次数、获胜、失利、所在年龄组世界排名。缺失值显示“—”，真实的零显示 0；不会换算 NTRP，也不会用本地赛事计算 UTR 战绩或世界排名。

## 存储与接口

- `users.utr_rating`：已有 UTR 积分字段。
- `users.ntrp_level`：已有 NTRP 字段。
- 新表 `user_utr_records`：`user_id` 为主键及用户外键，保存可空的 `matches_played`、`wins`、`losses`、`world_rank`、`age_group`，以及创建、更新时间。
- Alembic `20261016_utr_records`，前置 `20261015_entry_teams`。只新增表，不制造历史数据；无记录或 NULL 均作为尚未同步处理。
- 响应为上述字段的平铺结构（UTR 对应 `rating`），另含昵称、头像和 NTRP。外部 UTR 同步接口由用户后续提供，本次没有自动抓取或同步任务。
- 本次经用户确认的一次性账号数据与角色调整在发布后单独执行，不把个人数据或用户 ID 写入通用迁移。

页面说明：所有数据（包括世界排名）均来自 UTR 官网。世界排名仅代表所在年龄段在 UTR 系统中按积分排序产生的世界排名，不能严格代表真实水平差异。

## 验证

- 前端类型、205 项测试、生产构建、上传 dry-run 通过；Wot 用法检查无错误，保留既有警告。
- 隔离 H5 页面验证普通用户、俱乐部管理员无卡片、无战绩请求；系统管理员可进入；角色降为普通用户后拒绝访问。验证接口失败重试、真实 0、NULL、320/390px 布局。
- 后端鉴权与数据库真实值测试包含匿名 401、普通用户/俱乐部管理员 403、系统管理员 200、同 token 降权 403、NULL 与真实零的区分。
- 独立本地 MySQL 8.4 验证空库升级、前一版本用户数据保留、新表 NULL、正式战绩数据及重复升级保留。
- CI 增加 UTR 接口测试及 MySQL 迁移测试。

## UTR 来源数据解析

`app.services.utr_records.parse_utr_snapshot()` 接受完整来源快照：`label` → 年龄组、`lose` → 失利、`played` → 比赛场次、`rank` → 世界排名、`rating` → UTR、`won` → 获胜。数字字符串解析为整数/Decimal，显式 NULL 或空字符串保留为空；缺少字段、非法数字和越界值拒绝导入，不推导数值。

`import_utr_snapshot(db, user_id, payload)` 使用用户表主键 `users.id`（微信 ID），锁定用户行，按主键创建或更新 `user_utr_records`。同一事务更新已有的 `users.utr_rating`；NTRP 和角色不受影响，提交由调用方负责。重复导入更新同一记录，后续 UTR 同步接口可调用此服务，本次没有新增公开写接口。

数据库实际结构已核对：`user_utr_records.user_id` 是主键，同时外键指向 `users.id`；没有重复战绩记录，用户主键与微信 openid 一致。页面移除积分和 NTRP 数字下方的辅助说明文字，保留字段标题。
