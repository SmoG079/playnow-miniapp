# 腾讯云正式环境部署核查

核查日期：2026-10-07（北京时间）。服务器：`101.34.213.125`。

## 本次完成

- SSH：`ssh ubuntu@101.34.213.125`，本机已有密钥可登录；Docker 命令需使用 `sudo -n docker`。
- 创建数据库、API 容器 uploads、服务器部署配置的备份；未修改生产业务表、迁移版本或重启服务。
- 使用独立临时数据库恢复 SQL 备份，15 张表全部恢复，逐表行数与核查快照一致；验证后已删除临时库。
- 容器上传目录的归档包含 2 个文件；SQL gzip、上传归档可读取，SQL 有完整结束标记。
- 备份包含生产环境配置和证书，保存在服务器 root 专用目录，目录权限 700，文件权限 600；没有将业务数据、密码、私钥下载到本地或写入仓库。

服务器备份位置：`/var/backups/playnow/20261007-113859`。

| 文件 | 内容 |
|---|---|
| `club_db.sql.gz` | InnoDB 单事务导出的结构和数据，包含触发器、事件和存储程序 |
| `container-uploads.tar.gz` | 当前 API 容器 `/app/uploads` |
| `server-config-and-host-uploads.tar.gz` | 当前部署目录、旧 Compose/.env、宿主机 Nginx 配置及证书、Cron 配置 |
| `schema.json` | 实际数据库字段、索引、外键、逐表行数 |
| `manifest.json` | 初始备份文件大小与 SHA-256 |
| `restore-verification.json` | 临时库恢复验证结果 |

备份当前仍在同一台服务器。数据库、文件和配置分别采集，并非跨系统的同一原子快照；数据库恢复已验证，应用整体恢复、异地备份与自动备份尚未完成。

## 现有部署

- Ubuntu 22.04，x86_64，4 核，3.3 GiB 内存，核查时可用约 604 MiB，无 Swap；磁盘剩余约 25 GiB。
- Docker 26.1.3，Compose 2.27.1。
- API/MySQL/Celery 来源：`/home/ubuntu/playnow-miniapp`；Redis 来源：`/opt/playnow-miniapp`。两套目录使用相同 Compose 项目名。
- API/Worker/Beat 使用 GHCR `latest` 镜像，自 2026-06-24 北京时间起运行；没有可据以确认源码 commit 的镜像 revision 标签。
- MySQL 8.0.46，15 张业务表，MySQL 数据卷 `playnow-miniapp_mysql_data`；没有 `alembic_version` 表。
- API 容器没有 uploads 挂载；Redis 使用匿名数据卷。
- 实际入口是宿主机 Nginx，监听 80/443/8443；外部 `https://www.tennisplaynow.site:8443/health` 返回 200。443 本机外部访问被重置，原因待核查。
- TLS 证书北京时间 2026-12-05 07:59:59 到期；未发现常见 ACME/Certbot 目录或续期定时任务。
- 3306/6379/8000 绑定所有网卡，主机 UFW 未启用；腾讯云安全组未核查。
- GHCR `/v2/` 返回 401，说明网络可达；认证及镜像下载尚未验证。

## 数据库对齐结论

实际表集合与当前模型的 15 张表一致，无模型所需字段缺失；但实际结构不对应一个完整迁移版本，不能直接执行 `upgrade head` 或 `stamp head`。

字段/约束检查范围：字段存在性、类型、可空性，模型声明的索引、唯一约束和外键。未全面比较服务端默认值、字符集、排序规则、触发器及事件。下面的差异来自实际数据库与当前仓库 `backend/app/models/models.py` 的对比。

差异分类：`type` 3 项，`nullable` 25 项，`extra_column` 5 项，`missing_index` 1 项，`missing_unique` 1 项，共 35 项。

| 表/字段 | 差异 | 当前数据库 | 模型要求 |
|---|---|---|---|
| `users.ntrp_level` | `type` | `varchar(16)` | `decimal(2,1)` |
| `clubs.opening_time` | `nullable` | `True` | `False` |
| `clubs.closing_time` | `nullable` | `True` | `False` |
| `clubs.split_ratio` | `nullable` | `True` | `False` |
| `clubs.view_count` | `type` | `integer` | `bigint` |
| `clubs.view_count` | `nullable` | `True` | `False` |
| `clubs.exposure_count` | `type` | `integer` | `bigint` |
| `clubs.exposure_count` | `nullable` | `True` | `False` |
| `clubs.status` | `nullable` | `True` | `False` |
| `club_members.role` | `nullable` | `True` | `False` |
| `venues.max_capacity` | `nullable` | `True` | `False` |
| `venues.status` | `nullable` | `True` | `False` |
| `venues.sort_order` | `nullable` | `True` | `False` |
| `venues.close_time` | `extra_column` | `—` | `—` |
| `venues.closing_time` | `extra_column` | `—` | `—` |
| `venues.open_time` | `extra_column` | `—` | `—` |
| `venues.opening_time` | `extra_column` | `—` | `—` |
| `venues.slot_interval_minutes` | `extra_column` | `—` | `—` |
| `venue_time_slots.status` | `nullable` | `True` | `False` |
| `booking_orders.slot_id` | `nullable` | `False` | `True` |
| `booking_orders.status` | `nullable` | `True` | `False` |
| `settlement_records.split_ratio` | `nullable` | `True` | `False` |
| `settlement_records.status` | `nullable` | `True` | `False` |
| `settlement_records.scheduled_at` | `nullable` | `True` | `False` |
| `settlement_records` | `missing_index` | `—` | `status,scheduled_at` |
| `settlement_records` | `missing_unique` | `—` | `out_order_no` |
| `match_posts.approval_required` | `nullable` | `True` | `False` |
| `match_posts.status` | `nullable` | `True` | `False` |
| `match_registrations.status` | `nullable` | `True` | `False` |
| `tournaments.lock_venue` | `nullable` | `True` | `False` |
| `tournaments.current_participants` | `nullable` | `True` | `False` |
| `tournaments.entry_fee` | `nullable` | `True` | `False` |
| `tournaments.status` | `nullable` | `True` | `False` |
| `tournament_registrations.status` | `nullable` | `True` | `False` |
| `notifications.is_read` | `nullable` | `True` | `False` |

重点：

- `booking_orders.slot_id` 线上为 NOT NULL，模型允许 NULL。
- `users.ntrp_level` 线上为 varchar(16)，模型为 decimal(2,1)。核查时不符合单数字及可选一位小数格式的非空值数量为 0。
- 24 个需要收紧 NOT NULL 的字段，核查时 NULL 数量全部为 0；实际迁移前需要重新校验，避免并发写入改变结论。
- 结算表缺少 `(status, scheduled_at)` 索引和 `out_order_no` 唯一约束。
- venues 有 5 个当前模型未使用的历史字段；应先保留，避免丢失历史信息。
- `match_posts.club_id` 已允许 NULL，但这不足以证明整体数据库达到最新迁移版本。
- 历史迁移链存在重复添加已有字段等问题；初始迁移还不能完整覆盖当前 15 张表及模型演进，需要同时验证空库路径。

## 后续执行顺序

1. 修复迁移链并提供明确的现有库接管路径；先在恢复副本中验证，不能直接在生产库试跑。
2. 验证迁移后与目标模型匹配、原有逐表数据未丢失，并单独验证空库升级路径。
3. 将容器 uploads 复制到持久化位置，校验文件后再配置挂载；切换时处理新增上传文件。
4. 使用一套正式 Compose 配置，保留现有 MySQL 卷和 Redis 数据；API 通过宿主机 Nginx 对外，不再启动占用 80/443 的 Nginx 容器。
5. 统一 GitHub 环境名及分支限制，适配 uni-app 检查/构建/上传，按 commit SHA 发布并补齐回滚和外部验收。

本次尚未执行任何生产迁移或部署。备份核验后 API 健康检查仍返回 `{"status":"ok"}`。

## 后续进展：迁移修复已完成隔离验证

- 已增加固定快照的 `20261007_schema_alignment` 迁移，以及默认只读的 `backend/scripts/adopt_legacy_database.py` 接管入口。
- 历史字段重复添加问题已修复，保留已有迁移 revision 标识。
- 3 项 MySQL 集成测试通过：空库完整升级与重复执行、恢复副本接管且全表数据哈希不变、非法 NTRP/NULL/重复结算单号在 DDL 前拒绝。
- 演练使用独立临时库、专用数据库账户和一次性容器，完成后全部清理。
- 新脚本在生产库的只读预检查通过，计划执行 28 个结构操作；35 项差异中的同一字段类型/可空性变更会合并为一个操作。
- **生产库尚未执行接管、未登记迁移版本、未修改业务表。** 实际迁移需结合正式部署维护窗口，重新备份并停写。
- 详细流程见 [数据库迁移操作文档](database-migration-runbook.md)。下一步整理持久化文件与正式 Compose 配置。

## 后续进展：正式 Compose 与持久化准备完成

- 新增独立 `compose.production.yml`，复用宿主机 Nginx、现有 MySQL/Redis 卷及网络；API 只绑定 loopback，数据库和 Redis 不发布端口。
- 在服务器暂存 `.next` 配置及 root 专用环境文件，保留已有凭据，未切换线上配置。
- 容器内 2 个上传文件已复制至宿主机 `backend/uploads`，哈希核对通过；两个临时容器验证文件可跨容器重建保留，探针已删除。
- 新健康检查实测正常依赖成功、Redis 不可达失败；新增 Docker 构建忽略规则。
- 当前 API 镜像无仓库 digest，仅本地 ID；正式发布需要流水线构建的 SHA 镜像，当前暂存镜像不能直接切换。
- Beat 调度文件与 Redis 最新内存状态需要在正式停写窗口同步/持久化。
- 生产服务、公开监听端口和数据库仍未变动。详细步骤见 [正式 Compose 操作文档](production-compose-runbook.md)。下一步接入 GitHub Actions 和正式发布脚本。

## 后续进展：CI/CD 发布入口已实现

- GitHub Actions 统一使用 `product` 环境，已将环境分支限制改为 `master`，设置核验过的服务器目标及主机公钥 Secret；既有 SSH 私钥 Secret 保持原值。
- PR 执行后端/前端验证和镜像试构建；正式镜像使用完整 commit SHA，并带 revision 标签。体验版上传使用同次前端构建 artifact，默认关闭。
- 服务器发布入口使用文件锁、数据库/文件备份、迁移前停写、HTTPS/依赖/Worker 验收；没有首次接管记录时自动发布会提前拒绝。
- 表结构未变化时允许恢复旧应用版本；迁移失败或结构改变后发布失败则保持应用停写，保留 root 专用恢复资料。
- 本地前端 8 项测试、类型检查、生产构建、上传 dry-run，以及发布控制流 8 项测试、Actions 静态检查通过。
- 真实 GitHub CI 和首次手动部署需继续验收，不能把单元测试当作完整生产发布已成功。详见 [CI/CD 文档](cicd-wechat-miniprogram.md)。

## 后续决定：真实支付与退款暂缓

- 2026-10-07，负责人明确要求真实支付与退款暂时不处理，记录文档后继续流水线。
- 当前预订支付直接标记已支付、取消不计算退款；保留实现不变。10 项对应历史测试显式标记待办并从 CI 排除，另两项详情权限测试修正过期模拟数据，继续执行权限断言。
- 完整现状、验收边界和恢复清单见 [支付与退款待办](deferred-booking-payments.md)。

## 首次发布进展：镜像传输调整

- PR #5 已合并；master 版本 `bbd85330f86841bf235199466f59ecd7cc77b605` 的 CI、镜像推送、GitHub SSH 凭据及服务器 GHCR 登录通过。
- 普通 push 发布在首次接管保护处拒绝，未停止服务；手动 bootstrap 随后进入镜像拉取阶段，腾讯云到 GHCR 镜像层的下载明显偏慢。
- 在任何停写/迁移之前结束了该拉取尝试，确认原有 API、Worker、Beat 仍运行。
- 发布传输改为 Runner 拉取并导出镜像，经 SSH 传到服务器，校验 SHA256 后加载，再检查镜像 revision。后续首次接管仍需通过实际工作流验收。
