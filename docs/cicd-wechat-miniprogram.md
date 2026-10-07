# PlayNow 正式环境 CI/CD

工作流：`.github/workflows/deploy.yml`。部署环境统一为现有 `product`，允许 `master`。环境 Secrets 在引用该环境的部署任务中读取；PR 检查不依赖部署凭据。

## 工作流行为

- PR → master：后端测试、空库迁移及重复迁移、发布流程失败边界测试、uni-app 类型检查/单元测试/小程序生产构建，以及后端 Docker 镜像试构建。不会部署或推送镜像。
- push → master：上述后端/前端验证通过后，构建并推送 `ghcr.io/smog079/playnow-miniapp-api:<完整 commit SHA>`，SSH 同步版本化部署包，部署并验收。没有首次接管成功标记时，发布脚本会在停止服务前拒绝自动部署。
- 手动触发：`deploy` 默认 false；首次维护窗口选 `deploy=true`、`bootstrap=true`；之后手动部署只选 `deploy=true`。
- 小程序上传默认关闭。手动选择 `upload_miniprogram=true`，或将 GitHub 变量 `AUTO_UPLOAD_MINIPROGRAM=true`，才在后端部署成功后上传同一工作流构建的小程序体验版。审核与正式发布仍由微信平台流程完成。

小程序产物是 `frontend/dist/build/mp-weixin`。上传任务下载前端验证任务保存的同一 SHA 产物，不再依赖已删除的 `miniprogram/`。CI 使用 Node 20；本机 dry-run 不加载 miniprogram-ci，实际上传请使用 Node 20。

## GitHub product 环境

部署 Secrets：

| 名称 | 值或用途 |
|---|---|
| SERVER_HOST | 101.34.213.125 |
| SERVER_USER | ubuntu |
| SERVER_PORT | 22 |
| SERVER_PROJECT_PATH | /home/ubuntu/playnow-miniapp |
| SERVER_SSH_KEY | 既有服务器 SSH 私钥，保留现有值 |
| SERVER_KNOWN_HOSTS | 通过已有 SSH 连接核验的主机公钥记录 |

已将环境分支限制从 `main` 修正为 `master`，并写入已核实的服务器目标及主机公钥；没有输出、下载或替换 GitHub 中既有的私钥 Secret。GitHub 无法读回该私钥，首次 CI 的 SSH 阶段仍需验证它是否有效。

体验版上传需要另外设置 `WX_MINIPROGRAM_PRIVATE_KEY` 或 `WX_MINIPROGRAM_PRIVATE_KEY_BASE64`；`WX_MINIPROGRAM_ROBOT` 可选，默认为 1。这些 Secret 当前未配置，所以自动上传保持关闭。

SSH 使用严格主机公钥核验。GHCR 使用工作流临时 GITHUB_TOKEN，经 SSH 标准输入登录到 root 专用临时 Docker 配置目录；运行结束清除该目录，不覆盖服务器已有 Docker 登录设置。

## 服务器发布步骤

运输入口 `scripts/remote-deploy.py` 只接受已核查的服务器目标和完整 SHA，将公开部署代码打包到服务器 `.releases/<SHA>-<run>-<attempt>`；不会上传 `.env` 或私钥。

服务器入口 `scripts/deploy-production.py`：

1. 获取服务器文件锁，验证首次接管模式与 `.deployment-ready.json` 状态。
2. 拉取 SHA 镜像，检查镜像 revision 标签、迁移/健康脚本、Compose 和当前数据卷/凭据一致性。
3. 停止 Beat、API 和 Worker，等待正在执行的任务退出；同步 uploads 和停止后的 Beat 状态，保存 Redis RDB。
4. 创建 root 专用数据库与持久化文件/配置备份，验证 SQL 结束标记。
5. 使用新镜像的一次性容器执行迁移。首次接管走明确的 adoption 脚本；后续正常 `alembic upgrade head`。
6. 首次切换接管 MySQL/Redis 配置；后续只重建 API/Worker/Beat。
7. 验证 API、MySQL、Redis、外部 HTTPS 和 Celery Worker，成功后记录 SHA、版本目录、备份路径和 schema 是否变化。

这是单机停写维护式发布，需要短暂中断 API；没有承诺零停机。首次接管还会重建基础服务以收回公开数据库端口，必须放在维护窗口。

失败处理：

- 预检查失败：不停止服务。
- 迁移尚未开始时失败：重新启动原容器。
- 迁移完成且表结构没有变化、日常发布启动失败：恢复上一应用版本。
- 迁移中失败，或结构变化后发布失败：保持应用停止，保留备份和 root 专用日志，等待排查恢复；不会自动 downgrade 或盲目恢复旧镜像。

流水线使用串行 concurrency，不取消正在进行的发布；服务器文件锁也避免不同入口同时发布。日志与备份可能含有敏感配置，不上传为 GitHub artifact；没有自动删掉旧镜像或数据卷。

## 验证与当前边界

- 真实预订支付及取消退款规则按 2026-10-07 决定暂缓；10 项历史测试显式排除，保留待办，详见 [支付与退款待办](deferred-booking-payments.md)。CI 通过不表示真实收款/退款已验收，其余后端测试仍是发布条件。

- 发布控制流的 8 项测试已在本地通过，覆盖首次接管、预检查失败、迁移失败、schema 未变回退及 schema 改变停写。
- 数据库空库/恢复副本接管及非法数据拦截已在服务器隔离临时库通过，见 [迁移文档](database-migration-runbook.md)。
- 持久化和正式 Compose 已在服务器通过验证，见 [Compose 文档](production-compose-runbook.md)。
- 首次真实 SHA 镜像、GitHub 私钥 Secret、远程镜像拉取和全链路发布还需实际 CI/维护窗口验收。仓库改动没有触发生产部署。

本地前端检查：

```bash
npm ci
npm ci --prefix frontend
npm run check:miniprogram
```

实现参照 GitHub 的 [部署环境与并发控制](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments) 及 [任务间构建产物传递](https://docs.github.com/en/actions/tutorials/store-and-share-data)。
