# 2026-10-07 正式环境首次部署验收

首次接管已成功完成。服务器为 `ubuntu@101.34.213.125`，项目目录为 `/home/ubuntu/playnow-miniapp`。

## 发布结果

- 正式版本：`4a999473e0b3cfc0e6e50faaaffb708b7bd11027`。
- [GitHub Actions 首次接管工作流](https://github.com/SmoG079/playnow-miniapp/actions/runs/37587141218)全部成功；小程序上传按参数关闭。
- [PR #5](https://github.com/SmoG079/playnow-miniapp/pull/5)、[PR #6](https://github.com/SmoG079/playnow-miniapp/pull/6)、[PR #7](https://github.com/SmoG079/playnow-miniapp/pull/7) 已合并。
- 发布镜像：`ghcr.io/smog079/playnow-miniapp-api:4a999473e0b3cfc0e6e50faaaffb708b7bd11027`。
- 版本目录：`/home/ubuntu/playnow-miniapp/.releases/4a999473e0b3cfc0e6e50faaaffb708b7bd11027-37587141218-1`。
- 备份目录：`/var/backups/playnow/20261007T074722Z-4a999473e0b3`，包含完整 SQL、持久化文件和切换前配置。SQL 完成标记已验证；root 专用验收记录为该目录下 `deployment-verification.json`。
- 首次接管成功记录：服务器 `/home/ubuntu/playnow-miniapp/.deployment-ready.json`。其中时间记录为备份开始时间，不是发布完成时间。

## 已确认

- 执行 28 个结构操作后登记 `20261007_schema_alignment`；新应用中只读检查确认没有待执行的结构操作。
- API、MySQL、Redis 为 healthy；Worker 的 Celery ping 成功，Beat 运行。
- [公开健康接口](https://www.tennisplaynow.site:8443/health)在服务器和本机均返回 `{"status":"ok"}`。
- 流水线检查持久化上传文件的公开内容哈希，验收通过。
- API 仅发布 `127.0.0.1:8000`；MySQL 3306/33060、Redis 6379 不再发布宿主机端口。宿主机 Nginx 保留。
- MySQL 仍使用 `playnow-miniapp_mysql_data`；Redis 仍使用原匿名卷 `2ab5d3c5f4b3d423b0b82ac457e4e47ac696961d7ed170ef484eb5b1512b7aa8`。
- uploads、日志、Beat 调度状态和证书目录已使用正式配置的宿主机挂载。
- 镜像归档完整 SHA256 校验通过；传输归档、分段及临时目录已清理，服务器没有保留流水线 GHCR 凭据。
- 首次接管完成后，以 `--image-loaded --check-only` 验证日常发布入口成功，没有停止服务。尚未额外执行第二次完整日常发布。

## 后续发布

`master` 的 push 在前后端检查通过后自动部署后端，不再需要 `bootstrap`。手动发布使用 `deploy=true`、`bootstrap=false`。镜像经 Runner 拉取、压缩后采用最多 16 路 SSH 分段传输，服务器按序重组并验证，再进入单机停写维护窗口。

早期 GHCR 镜像层下载和单连接 SSH 传输偏慢；已在停写前结束这些尝试并改用并行传输。首次成功归档约 209 MiB；整体发布时间仍取决于跨境网络。13 项原部署/传输测试加 2 项分段测试，共 15 项通过；真实工作流也已成功。

真实支付、退款暂缓，当前占位行为及恢复清单见 [支付与退款待办](deferred-booking-payments.md)。小程序体验版上传仍默认关闭，需另外配置微信上传凭据。工作区未提交的其他功能改动不属于上述正式版本。


## 全流程修复后的最终部署

最终线上后端版本 `d9a2e6bf5e332832ecfc2c9cf0e2bd1420df468f`，流水线 [37596946362](https://github.com/SmoG079/playnow-miniapp/actions/runs/37596946362) 成功。修复消息/分账路由、日期范围排期、时段默认价、回复评论删除、未登录响应、生产开发登录、前端分账权限及通知状态、跨设备约球与赛事报名记录，以及特殊时段报价/订单金额一致性。

实际正式镜像在隔离环境的 86 项业务 HTTP 检查通过，公网 36 项检查通过，测试数据和图片已清理。备份 `/var/backups/playnow/20261007T091020Z-d9a2e6bf5e33`。新微信小程序构建包 `/tmp/playnow-e2e-release-d9a2e6b` 已准备，开发者工具服务端口仍关闭，真实微信运行、上传和正式发布尚未完成。真实支付退款依约继续暂缓。

详细记录和机器可读检查结果位于已附加验收工作区：`/Users/smog056/.codex/worktrees/full-flow-verification/playnow-miniapp/docs/full-flow-verification-20261007.md`。
