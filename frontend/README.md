# PlayNow Wot UI 前端

这是原生微信小程序的 UniApp + Vue 3 + Wot UI v2 迁移版本，业务请求连接现有线上后端：

`https://www.tennisplaynow.site:8443/api/v1`

## 微信开发者工具调试

```bash
cd frontend
npm install
npm run dev:mp-weixin
```

随后在微信开发者工具中导入 `frontend/dist/dev/mp-weixin`。项目已配置原小程序 AppID `wxfad430ba15c6c3e2`。首次调试请确认后端域名已加入微信公众平台的 request/uploadFile/downloadFile 合法域名。

> 2026-09-06 实测：`www.tennisplaynow.site:8443` 服务可达，HTTPS 证书有效期为 2026-09-06 至 2026-12-04。开发构建已关闭本地合法域名校验；真机预览仍需确认该地址已加入公众平台的 request/uploadFile/downloadFile 合法域名。

生产构建：

```bash
npm run typecheck
npm test
npm run build:mp-weixin
```

构建产物位于 `frontend/dist/build/mp-weixin`。

## 当前约束

- 场地预约支付沿用当前后端的开发占位支付逻辑。
- 群聊、球友公开资料和“我的报名”在旧版即为空壳；迁移版保留对应入口和明确空态。
- 赛事报名支付仍调用微信支付，需真机及商户配置才能完成验收。
