# 腾讯天气接入与定位缓存复用（2026-10-14）

天气使用腾讯位置服务 WebService 开发密钥。该 Key 与地图 WebService 通用，是否可调用取决于启用服务、权限及分配额度，不另引入前端天气密钥。官方入口：[申请密钥](https://lbs.qq.com/dev/console/key/add)、[管理密钥](https://lbs.qq.com/dev/console/key/manage)、[分配额度](https://lbs.qq.com/dev/console/quota/account)；操作原则见 [腾讯 WebService 入门指南](https://lbs.qq.com/service/webService/webServiceGuide/overview)。

## 获取与配置

1. 登录腾讯位置服务控制台，完成页面要求的开发者注册/认证，创建应用和 Key。控制台若展示“我的应用”，从应用内添加密钥。
2. 给该 Key 启用 **WebService API**。腾讯官方说明中，未启用返回 199。天气使用 `/ws/weather/v1/`，逆地址解析使用 `/ws/geocoder/v1/`；具体天气参数见 [腾讯官方 API 参考](https://github.com/TencentLBS/tencentmap-webservice-skill/blob/main/references/api-location-weather.md)。
3. 在额度管理给该 Key 分配所需接口的额度，检查天气日调用量和 QPS；仅创建 Key 不等于已分配额度。若返回 113，需开通对应功能权限；121 表示日额度不足。状态码见 [腾讯官方 WebService 技能说明](https://github.com/TencentLBS/tencentmap-webservice-skill/blob/main/SKILL.md)。本地测试环境与生产环境有不同出口 IP，若启用了 IP 白名单，分别核对来源；112 表示 IP 未授权。
4. 服务端环境文件填写：

   ```dotenv
   TENCENT_MAP_KEY=你申请的腾讯位置服务Key
   TENCENT_MAP_SK=开启签名校验后对应的SK
   ```

   未启用签名校验时 `TENCENT_MAP_SK` 留空；启用时必须与 Key 配对，代码已支持签名。该 SK 是腾讯位置服务 WebService 的签名密钥，不填写 COS 或腾讯云其它服务的密钥。

正式 Compose 从 `APP_ENV_FILE` 读取应用环境，默认 `./backend/.env`。Key 应写入该文件；仅在 Compose 的 `.env.production` 增加变量不会自动传给 API。更新环境文件后，需要重建 API 容器才能让 Docker 重新注入变量，单纯 `docker restart` 不会更新创建时的环境。本次代码改动还需按既有发布流程部署后端，并独立上传新版小程序；本轮未执行这些发布操作。

## 当前请求链路

- 逆地址解析 `/discovery/location-city` 返回城市、省份、地区和已有 `ad_info.adcode`；前端不为天气重复解析地址。
- 当前会话天气查询复用定位成功且绑定该城市的坐标，直接传 `lat/lng`。
- 城市缓存持久化城市与行政区划编码，重开应用用 `adcode` 查天气。精确坐标仍仅存在于会话内，不写入持久化 Storage。
- 手动选城传入微信地区选择器返回的 `code`：一般城市选市级码，直辖市选省级码，省直辖县级市选县级码。切到另一个城市时替换天气位置，不复用旧城市 GPS；用于距离排序的 GPS 与天气位置分别处理。
- 天气 API 必须有行政区划编码或成对的有效坐标。没有位置的旧缓存/旧客户端不会触发正向地理编码，需重新选择地区或定位一次。无编码时前端展示重新选择提示，不自动发起权限请求。
- 服务端天气调用已移除地址正向解析，只请求腾讯天气。仍校验供应商城市与所选城市一致，缺失/错误温度不显示为成功。
- 客户端缓存及并发共享的键包含城市、省份和位置；服务端缓存同样包含位置，防止同名/同城不同位置错误复用。供应商错误日志记录状态码或异常类型，不记录带 Key 的 URL、原始供应商错误消息或密钥。

## 验证与限制

- Python 3.12 后端全量测试 **408 passed、28 skipped、10 deselected**；天气/城市专项 **35 passed**。新增位置缺失、无效经纬度、行政编码、签名、一次天气请求及逆解析编码保留验证。没有修改历史暂缓支付测试的标记或断言。
- Node 20 前端类型检查、**163 项测试**通过。覆盖会话坐标传递、重开应用恢复编码、手动选城替换绑定、直辖市/省直辖县级市、无位置不请求、同城不同位置缓存隔离及异步切城。
- 小程序生产构建、上传 dry-run、Wot lint 通过。Wot 保留既有 10 项组件元数据识别告警，无错误。未实际上传或部署。
- 本机现有 `backend/.env` 含 Key/SK，配置代码默认值仍为空；本轮没有修改真实环境文件。新路径直接用坐标、行政编码联调时，腾讯天气均返回 **121**，因此本机仍需可用的天气额度。没有核对线上 Key 是否与本机相同，不能将本机配置状态当作线上配置状态。
- 未执行微信地区选择器真机验收；字段使用微信原生 region 事件的 `code`，缺失时保持安全回退，不向供应商重复解析地址。旧缓存仅城市名需重新选择一次。
