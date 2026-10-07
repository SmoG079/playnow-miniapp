# 真机微信登录排查（2026-10-07）

## 已确认原因

真机显示 `WeChat login failed: invalid code`，线上存在 `/auth/login` 的 400 响应。实际运行时 `wx.getAccountInfoSync()` 返回 AppID `wxe6fd99528373b676`（e球有约），构建目录的 `project.config.json` 也已被改成该值，但源码 manifest / project.wx.json 及线上 API 配置仍为 `wxfad430ba15c6c3e2`。因此登录凭证所属小程序与后端兑换配置不一致。后端旧 AppID 和 AppSecret 均已配置；排查未输出密钥或登录凭证。

用户确认正式切换到“e球有约”。源码 AppID 已统一为 `wxe6fd99528373b676`，新增登录前运行时 AppID 校验，拦截构建配置与源码不一致的登录，同时增加登录防重复提交。25 项前端测试及完整小程序构建、上传 dry-run 通过；补充构建配置一致性回归后，类型检查及 26 项前端测试通过。

## 配置切换与验证

用户已提供匹配凭据，写入本机 backend/.env（权限 600，Git 忽略），未输出密钥。经服务器请求微信 token 接口验证有效后，获得部署互斥锁，备份环境文件，仅更新服务器微信凭据并重建 API / Worker / Beat。镜像 b205bab6f1fc47fde954612efd5fec9369535f8b 保持不变，未部署赛事改造，未执行迁移。服务器备份位于 /var/backups/playnow/wechat-appid-switch-20261007T140834Z，权限仅 root 可读。旧 wx:access_token 缓存键已检查并删除，原本无缓存。

健康接口返回 ok。开发者工具使用真实 wx.login 取得新 code 并调用生产 /auth/login，返回 HTTP 200 且签发 access/refresh token。验证仅输出是否签发，不输出 code、令牌或敏感用户资料。手机重新连接后的登录由用户复测，此项不等同手机真机验收。

微信账号身份与小程序关联；切换 AppID 后的旧用户数据和管理权限迁移需单独明确，不自动猜测账号对应关系或转移权限。
