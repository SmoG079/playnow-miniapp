# 正式 Compose 与持久化准备

## 使用方式

正式部署使用独立的 `compose.production.yml`，不与 `docker-compose.yml` 或旧 `docker-compose.prod.yml` 合并。它只定义 API、MySQL、Redis、Celery Worker、Celery Beat，使用宿主机现有 Nginx 提供 HTTPS。

配置差异：

- API 仅发布 `127.0.0.1:8000`，Nginx 继续代理该地址。
- MySQL/Redis 不再发布宿主机端口。需要临时访问数据库时通过 SSH 和容器内客户端操作；此次准备尚未改变实际监听端口。
- 显式引用现有外部卷和外部网络，避免新建空数据卷。原 MySQL 卷为 `playnow-miniapp_mysql_data`；原 Redis 匿名卷按实际完整名称引用。
- MySQL 与 Redis 固定到当前镜像的仓库 digest，保留现有密码；修改环境变量不会替已有 MySQL 数据库修改密码。
- API/Worker/Beat 使用同一提交 SHA 或仓库 digest 对应的新镜像；不使用 `latest`。
- uploads、各服务日志、支付公钥证书缓存和 Celery Beat 调度文件使用宿主机目录。私钥目录 `/app/certs` 只读，公钥缓存 `/app/pay-certs` 可写。
- `PUBLIC_BASE_URL` 明确设为当前可用地址 `https://www.tennisplaynow.site:8443`。
- API 健康检查同时验证 HTTP、MySQL 查询和 Redis 认证连接。
- `backend/.dockerignore` 排除真实环境变量、证书、上传文件、日志和虚拟环境，避免进入发布镜像。

Compose 的外部卷生命周期与应用分离，见 [Docker 外部卷文档](https://docs.docker.com/reference/compose-file/volumes/)。变量文件使用单引号保留密码中的 `$` 等字符，见 [Docker 变量解析文档](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation)。不要将解析后的 `docker compose config` 原文贴到聊天或 CI 日志，它含有凭据。

## 已在服务器准备的内容

服务器目录：`/home/ubuntu/playnow-miniapp`。

- `compose.production.yml.next`：待切换配置，当前未生效。
- `.env.production.next`：由运行容器的既有配置生成，root 拥有、权限 600。没有把凭据下载到本地。
- `prepare-production.py.next` 和 `validate-production.py.next`：本次准备脚本。
- `backend/uploads`：当前 2 个上传文件，已与容器文件逐项核对 SHA-256。
- `backend/logs/{api,celery-worker,celery-beat}`、`backend/certs`、`backend/pay-certs`、`backend/celerybeat`：已建立持久化目录。

现有 API 镜像只有本地 image ID，没有 GHCR RepoDigest。因此待切换环境暂时引用这个不可变本地 ID，仅用于配置核查。它是旧代码，不包含新健康检查/迁移脚本，**不可直接作为正式切换镜像**。流水线完成新镜像构建与推送后，必须将 `API_IMAGE` 换成 `ghcr.io/smog079/playnow-miniapp-api:<完整 commit SHA>` 或仓库 digest，并拉取后验证。

线上旧 Compose、环境文件、容器、Nginx 及业务表保持原样。

## 验证结果

- 服务器 Compose 2.27.1 成功解析新文件，确认只包含 5 个服务，无容器 Nginx。
- 既有数据卷、网络、MySQL/Redis 镜像与应用凭据全部一致。
- 两个一次性容器先后挂载 uploads，第一个写入探针，第二个读到相同内容；探针与容器已清理。
- 在当前 API 容器的独立 Python 进程中，新健康检查成功；模拟 Redis 不可达时返回失败。未修改长期运行进程的配置。
- Celery Beat 当前调度状态在容器内 `/app/celerybeat-schedule`，尚未迁到新目录；需要停 Beat 后复制稳定状态。

验证记录在 `/var/backups/playnow/20261007-113859/compose-persistence-verification.json`，root 权限 600。

## 后续正式切换顺序

以下步骤尚未执行，需要与迁移和发布脚本串联，避免新代码先连接旧结构。

1. 流水线构建、推送并拉取带新迁移/健康脚本的 SHA 镜像，将其写入待切换环境文件。保留旧 API 镜像，作为应用回滚参考。
2. 在服务器执行配置与镜像验证：

   ```bash
   cd /home/ubuntu/playnow-miniapp
   sudo -n python3 validate-production.py.next --check-image
   ```

3. 在维护窗口暂停 API 写入、停止 Worker 和 Beat，重新备份数据库、uploads 与部署配置，确认无任务还在执行。使用新镜像的一次性容器执行数据库接管/升级，详见 [数据库迁移操作文档](database-migration-runbook.md)。
4. 删除旧 API 容器前再同步文件，并复制停止后的 Beat 状态：

   ```bash
   sudo -n python3 prepare-production.py.next --sync-files
   sudo -n docker cp club-celery-beat:/app/celerybeat-schedule backend/celerybeat/celerybeat-schedule
   ```

   当前是一个调度文件；如果届时有 `.dat/.dir/.bak` 等文件，需要一并复制。首次切换前核对源/目标校验值。复制应在 Beat 停止后完成。

5. Redis 卷保留的是持久化文件，不等同于最新内存状态。重建 Redis 前应在停止业务写入后执行认证的 SAVE 并备份 RDB；不要把认证密码写入命令参数或日志。
6. 确认迁移、文件同步及数据备份成功后，将 `.next` 文件切换为正式文件，使用唯一配置启动：

   ```bash
   sudo -n docker compose --env-file .env.production -f compose.production.yml up -d --no-build --wait --wait-timeout 180
   ```

   同名容器的配置接管可能重建 MySQL/Redis，因此应作为维护窗口操作。后续日常发布只更新 API/Worker/Beat，避免重复重建基础服务。
7. 验收 HTTPS、上传文件访问、微信登录、数据库/Redis、Worker/Beat 和版本记录；确定正常后再恢复流量。

不要运行旧流水线的两文件合并部署，也不要删除现有数据卷。新配置使用外部卷，但这不能替代经过恢复验证的数据库备份。
