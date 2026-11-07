# PlayNow Wot UI 前端

这是原生微信小程序的 UniApp + Vue 3 + Wot UI v2 迁移版本，业务请求连接现有线上后端：

`https://www.tennisplaynow.site/api/v1`

## 微信开发者工具调试

```bash
cd frontend
npm install
npm run dev:mp-weixin
```

随后在微信开发者工具中导入 `frontend/dist/dev/mp-weixin`。项目已配置原小程序 AppID `wxfad430ba15c6c3e2`。首次调试请确认后端域名已加入微信公众平台的 request/uploadFile/downloadFile 合法域名。

> 真机需要在公众平台配置 `https://www.tennisplaynow.site` 为 request、uploadFile 和 downloadFile 合法域名。旧版使用的 8443 地址继续保留。开发工具关闭域名校验不能替代真机验证。

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
