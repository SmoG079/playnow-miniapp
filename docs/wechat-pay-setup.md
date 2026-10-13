# 微信支付接入：平台直收模式

> 2026-10-13：**真实订场支付已恢复接入**（此前一版曾被回滚为占位，现已按 `WX_PAY_ENABLED` 双分支恢复）。生产开通后置 `WX_PAY_ENABLED=true` 即为真实收款；`false` 仅用于本地/CI。
> 同日实测发现：**443 因域名未完成 ICP 备案被腾讯云拦截**，微信回调从公网进不来 —— 已加入**主动查单兜底**并把回调地址先指向公网可达的 `8443`。详见第 1 节 C 小节与第 6 节风险。
> 同日补齐**退款侧兜底**（`POST /bookings/{id}/sync-refund`），并修掉一个会让退款兜底**完全静默失效**的 SDK 返回值解包 bug —— 详见第 3 节与第 7 节。

2026-10-12：本阶段目标是「让用户能把钱付进来」。平台用**自己的普通商户号直接收款**，资金进平台结算账户；**分账暂缓**（`PROFIT_SHARING_ENABLED=false`），俱乐部结算走线下。

> **结算账户不强制对公**：小程序主体是**个体工商户**，且经营者即负责人本人 —— 微信明确允许个体工商户用「对公账户」**或**「经营者个人银行账户」结算，本项目可用本人个人储蓄卡直接收款，无需开对公户。详见第 1 节 D 小节。

## 资金与数据流

| 步骤 | 动作 | 责任方 |
|---|---|---|
| 1 | 用户在小程序点「确认支付」 | 前端 `pages/booking/confirm.vue` |
| 2 | 后端校验订单归属/状态/时段锁，调微信 V3 JSAPI 统一下单 | `POST /api/v1/bookings/{id}/pay` |
| 3 | 返回 `pay_params`，前端拉起微信收银台 | `services/payment.ts` |
| 4 | 用户付款，**钱进平台商户号** | 微信 |
| 5 | 微信回调 `/api/v1/bookings/wx-notify`（验签+AES-GCM 解密） | 后端 |
| 5b | **回调不可达时的兜底**：前端调 `POST /bookings/{id}/sync-payment` 主动向微信查单 | `bookings.py::sync_booking_payment` |
| 6 | 置订单 `paid`、时段转 `booked`、发通知（5 和 5b 共用同一套落库逻辑） | `services/payment_callback.py` |
| 7 | T+1 自动结算到平台结算账户（对公户或经营者个人卡） | 微信 |

订单状态**只由微信返回的结果置为已支付** —— 要么是回调 `/wx-notify` 验签通过，要么是主动查单 `/sync-payment` 查到 `trade_state=SUCCESS`；两者复用同一个 `_handle_payment_success`，天然幂等。`/pay` 接口自己绝不标 `paid`。

### 退款链路（同一套兜底思路）

| 步骤 | 动作 | 责任方 |
|---|---|---|
| 1 | 管理员/平台点退款 | `POST /api/v1/bookings/{id}/refund` |
| 2 | 后端先落一条 `RefundRecord`（幂等），再调微信 V3 申请退款 | `bookings.py::refund_booking` |
| 3 | 钱退回用户，订单转 `refunding` | 微信 |
| 4 | 微信回调 `/api/v1/bookings/wx-notify`（`REFUND.SUCCESS/CLOSED/ABNORMAL`） | 后端 |
| 4b | **回调不可达时的兜底（三层）** | 见下表 |
| 5 | 订单转 `refunded`、释放时段、通知用户 | `payment_callback._handle_refund_callback` |

退款兜底的三层，互为冗余：

| 层 | 触发 | 延迟 | 入口 |
|---|---|---|---|
| 微信回调 | 自动 | 秒级 | `/wx-notify` |
| Celery `retry_failed_refunds` | 自动 | ≤ 300s | `tasks.py`（捞 `pending`/`failed` 记录） |
| Celery `poll_processing_refunds` | 自动 | ≤ 5min | `tasks.py`（捞 `processing` 记录） |
| **主动查单** | **用户/管理员点「刷新退款」** | **即时** | `POST /bookings/{id}/sync-refund` |

四者最终都汇聚到**同一个** `_handle_refund_callback`（主动查单会把微信查单返回的 `status` 映射成回调的 `refund_status` 字段后复用），因此不会出现多套状态机打架。

## 一、需要申请/开通的清单

### A. 微信公众平台（mp.weixin.qq.com）

| # | 事项 | 说明 |
|---|---|---|
| 1 | 有营业执照的主体 + 微信认证 | 硬门槛，个人主体不能开通微信支付；本小程序主体为**个体工商户**。认证 ¥300/年 |
| 2 | 小程序发布上线 | 硬门槛，未发布不能开通微信支付 |
| 3 | 「微信支付」入口 → 新申请商户号 / 绑定已有商户号 | 二选一 |
| 4 | 商户号发起绑定后，在小程序后台点「确认」 | 漏点这步支付会一直失败 |
| 5 | 服务器域名配置 request 合法域名 | 当前为 `https://www.tennisplaynow.site:8443`（可带端口） |
| 6 | 支付与交易 → 订单管理 → 交易类型设为**服务类** | 否则资金会冻结在「待确认收货」 |

### B. 微信支付商户平台（pay.weixin.qq.com）

| # | 事项 | 入口 | 说明 |
|---|---|---|---|
| 1 | 商户号 `mchid` | 申请 | 需营业执照、经营者（法人）身份证、**结算账户**；审核 1–5 个工作日。本项目**可用经营者本人个人储蓄卡**，无需对公户 |
| 2 | 技术负责人设为安全联系人 | 账户中心 | 否则拿不到开发参数 |
| 3 | 开通 **JSAPI 支付** | 产品中心 | 小程序支付共用此权限 |
| 4 | 关联小程序 AppID `wxe6fd99528373b676` | 产品中心 → AppID账号管理 | 关联后回小程序后台确认 |
| 5 | **APIv3 密钥**（32 位） | 账户中心 → API安全 | 回调 AES-256-GCM 解密必用 |
| 6 | **商户 API 证书** | 账户中心 → API安全 | 得到 `apiclient_key.pem` + **证书序列号**（`openssl x509 -in apiclient_cert.pem -noout -serial`） |
| 7 | **微信支付公钥**（必需） | 账户中心 → API安全 → 微信支付公钥 | 下载 `pub_key.pem` 并复制公钥 ID（`PUB_KEY_ID_...`）。⚠️ 微信已**下线平台证书**：不配这一项，`GET /v3/certificates` 返回 `RESOURCE_NOT_EXISTS`，SDK 构造抛 `No wechatpay platform certificate`，支付接口全部 5xx |
| 8 | **支付回调域名** | 产品中心 → 开发配置 | 填 `www.tennisplaynow.site`，**不带协议/端口/路径**。该项是商户维度的兜底配置；**实际回调地址以下单接口的 `notify_url` 参数为准**（本项目由 `WX_PAY_NOTIFY_URL` 控制）。⚠️ 备案未完成时该域名校验可能不通过，而 `notify_url` 传 `:8443` 不受影响 —— 见 C 小节 |

### C. 服务器与域名

| # | 事项 | 说明 |
|---|---|---|
| 1 | `www.tennisplaynow.site` 完成 **ICP 备案** | 微信配置合法域名与回调域名时都会校验；腾讯云 CDN 报 `CdnHostNoIcp` 说明此前未打通 |
| 2 | ~~Nginx 在 **443** 上反代 `wx-notify`~~ **✅ 早已配好，无需再动** | 2026-10-13 实测：`/etc/nginx/sites-enabled/api` 第四个 server 块即 `listen 443 ssl` → `proxy_pass http://127.0.0.1:8000`。服务器本地 `curl -k https://127.0.0.1/` → 200、`POST /api/v1/bookings/wx-notify` → 400（空 body 被 FastAPI 拒 = 确实到达后端）。证书 `CN=www.tennisplaynow.site`（SAN 含裸域），有效期至 **2026-12-04** |
| 3 | 私钥放到 `backend/pay-certs/apiclient_key.pem` | 该目录由 compose 挂载到容器 `/app/pay-certs`。**✅ 2026-10-13 已就位**：目录已存在（`root:root 700`，`create_host_path: false` 要求它先存在），`apiclient_key.pem` 已上传并 `chmod 600` |
| 4 | ⚠️ **443 从公网不可达（未备案拦截）** | 实测 `http://www.tennisplaynow.site/` → 302 跳 `dnspod.qcloud.com/static/webblock.html`（腾讯云未备案拦截页）；`https` 443 → TLS 握手被断。**这不是 nginx 配置问题，是 DPI 拦截**，只能等备案完成。对比：**8443 公网可达**（`/health` → 200），腾讯云只拦 80/443 |

> **「订单会一直 pending」的根因与处置（2026-10-13 已实施）**：微信回调必须从公网 POST 到 443 → 被未备案的 DPI 拦截 → 回调收不到 → 订单停在 `pending`（**但钱已进商户号，不会丢**）。配 nginx 解决不了这一环。已做的两件事：
>
> 1. **主动查单兜底**（不依赖备案，主手段）：新增 `POST /api/v1/bookings/{id}/sync-payment`，前端在支付返回后、支付结果页轮询时、以及「我的预约」点「刷新状态」时调用；后端调 `wxpay.query(out_trade_no=...)`（`GET /v3/pay/transactions/out-trade-no/{订单号}?mchid=`），命中 `SUCCESS` 即复用 `_handle_payment_success` 落库。**即使回调永远不通，支付闭环依然成立。**
> 2. **回调地址先指 8443**（公网实测可达，443 被拦）：`WX_PAY_NOTIFY_URL=https://www.tennisplaynow.site:8443/api/v1/bookings/wx-notify`。微信官方对非标准端口「不推荐、可能被拦」，但 V3 下单接口文档未明文禁止，实测成本为零。**备案完成后换回 443 的地址即可**（只改这一个环境变量）。
>
> 这两条互为冗余：8443 回调若被微信接受，就是即时到账；若不被接受，查单兜底也能在几秒内补齐状态。

### D. 结算账户怎么选（个体工商户不强制对公）

微信支付官方规则：**除个体工商户支持「法人账户或对公账户」结算外，其他主体类型（企业、政府/事业单位、其他组织）仅支持提供对公账户结算。**

| 选项 | 户名要求 | 说明 |
|---|---|---|
| 对公结算账户 | = 个体户营业执照全称 | 需先开对公户；个体户可凭执照 + 经营者身份证简易开户，年费通常可免 |
| 经营者个人账户 | = 营业执照上的**经营者本人** | 无需开对公户；微信 T+1 结算款打进该卡，须为**个人 I 类储蓄卡**，不能用信用卡 |

✅ **本项目可以直接用法人（经营者）本人的个人银行卡**：该个体户的经营者就是负责人**本人**。微信支付要求对私结算卡的户名与经营者完全一致 —— 本人用本人名下的卡，条件满足，**不需要开对公账户**。

选对私结算时的注意点：

- 卡必须是**经营者本人名下**的个人 **I 类储蓄卡（借记卡）**，不能用信用卡，也不能用家人或他人的卡
- 该卡在银行预留的手机号、身份证信息需与经营者一致，否则账户验证会失败
- 到账周期 T+1；微信结算款在银行流水中显示为财付通入账，建议**专卡专用**，便于对账
- 将来若需要开票、融资或升级为企业主体，届时再补对公户即可，不影响现在收款上线

无论选哪种，**经营款都要按规定申报纳税** —— 钱进个人卡不等于免税。

### E. 经营场景与照片要求（纯线上小程序**不需要门头照**）

商户入驻时「填写经营与行业信息」这一步要选**经营场景**，不同场景要交的材料完全不同 —— 门头照只属于**线下场所**：

| 经营场景 | 适用范围 | 要交的照片 |
|---|---|---|
| **小程序** ← **本项目选这个** | 通过小程序收款的线上经营 | **小程序 AppID + 小程序页面截图**（**不需要门头照**） |
| 线下场所 / 门店场所 | 实体门店、商场铺位、停车场 | 门头照 + 店内照，且**必须到店实地拍摄**（不支持从相册上传） |
| 流动经营 / 便民服务 | 摊位、自助售卖机、出租车 | 现场照片 2 张（全景 + 商品/车牌特写） |

官方《申请 JSAPI 支付权限指引（小程序支付场景）》原文：

> 当在"填写经营与行业信息"这一步骤时，经营场景选择**小程序**，并填写**小程序 APPID** 和**小程序页面截图**。
> 小程序页面截图（**选填**）：请提供展示商品/服务的页面截图/设计稿（最多 5 张），**若小程序未建设完善或未上线请务必提供**，图片需在 2M 内。

官方入驻流程指引里还有一句更直接的表述：

> 选择线下经营场景，需提供线下场所名称、具体地址、**门头与店内照片**；**若选择线下场所以外的经营场景（服务号或公众号、小程序、APP、PC网站、企业微信），则需要提供 APPID**。

因此：

- **不需要牌匾、门面、收银台照片**，也不存在"必须到店拍"的要求 —— 那些都只针对线下场景
- 真正的替代物是**小程序页面截图**（≤5 张、每张 ≤2M），建议顺序：首页 → 场地列表 → 场地详情 → 下单确认页 → 订单/我的预订页
- 如果小程序**尚未发布上线**，这一步**必须**提交截图或设计稿
- 入驻时填的 AppID 会**自动发起商户号与该 AppID 的授权绑定**，之后去小程序后台点「确认」即可（对应 A 表第 4 项）

**商户简称命名规则（个体户）**：不支持单纯用人名，可用「个体户 + 经营者名称」或「经营者名称 + 业务」命名，如"张三网球"；不支持"XX特约商户""800"这类无意义文案。该简称会直接显示在用户支付凭证上。

⚠️ **别为了"好过审"去选线下场所**：线下场景会进入后续的「经营场景检查」（监管要求到店实地拍摄、不支持相册上传，每次审核 3–7 个工作日）。纯线上业务选了线下，等于给自己埋一个长期的合规雷。

### F. 申请入口（在哪个网页申请）

| 入口 | 网址 / 路径 | 说明 |
|---|---|---|
| **① 小程序后台**（本项目推荐） | `https://mp.weixin.qq.com` 登录小程序 → 左侧「微信支付」（部分版本在【功能 → 微信支付】）→ 点「申请接入」→ 「注册微信支付商户号」 | AppID **自动带入**并自动发起绑定，少走一步 |
| ② 微信支付商户平台 | `https://pay.weixin.qq.com` → 点「接入微信支付」或「成为商家」→ 「注册微信支付商户号」 | 独立申请，拿到商户号后再去绑定 AppID |

两个入口都要**电脑端**操作（官方原文：「在**电脑端**前往微信支付商户平台申请页面」），扫码环节用手机微信完成。

关键点：

- 扫码的那个微信号会成为商户号的**超级管理员**（接收开户信息、有资金操作权限）→ **必须用经营者本人的微信号**，不要用店员或家人的微信号
- 超管若不是法人本人，需额外补充超管身份证件，审核更慢
- 小程序后台里的「微信支付」菜单**只有在小程序完成微信认证之后才可用**，没做认证先做认证
- 完整流程：创建申请单（扫码 + 填超管信息）→ 填商户资料（主体 / 法人 / 经营与行业 / 结算账户）→ **账户验证**（个体户可选「法人扫码验证」或「向财付通指定账户汇款」，前者即时）→ 审核 1~3 个工作日 → 签约（超管**刷脸**）→ 拿到 `mchid`
- 「微信支付商家助手」小程序是**申请之后**的经营管理工具（收进展通知、查流水、加安全联系人），**不是申请入口**
- 开通本身**不收费**；交易手续费按行业类目计，多数为 0.6%（以页面实际显示为准）

## 二、服务器配置

编辑 `/home/ubuntu/playnow-miniapp/backend/.env`（先备份）：

```ini
WX_MCH_ID=1751659629
WX_MCH_API_V3_KEY=<32位APIv3密钥>
WX_MCH_SERIAL_NO=<证书序列号>
WX_MCH_PRIVATE_KEY_PATH=/app/pay-certs/apiclient_key.pem
WX_PAY_CERT_DIR=/app/pay-certs
# 微信支付公钥：微信已下线平台证书，新商户必须用公钥模式（否则 SDK 构造即失败）
WX_PAY_PUBLIC_KEY_PATH=/app/pay-certs/pub_key.pem
WX_PAY_PUBLIC_KEY_ID=PUB_KEY_ID_<公钥ID>
# 443 未备案前先指 8443（公网可达）；备案完成后换回 https://www.tennisplaynow.site/api/v1/bookings/wx-notify
WX_PAY_NOTIFY_URL=https://www.tennisplaynow.site:8443/api/v1/bookings/wx-notify
WX_PAY_ENABLED=true
WX_PAY_DESCRIPTION=网球场地预订
PROFIT_SHARING_ENABLED=false
```

> **为什么必须配公钥（2026-10-13 实测结论）**：微信已停止向新商户签发**平台证书**，`GET /v3/certificates` 返回
> `{"code":"RESOURCE_NOT_EXISTS","message":"无可用的平台证书，请在商户平台-API安全申请使用微信支付公钥"}`。
> 而 `wechatpayv3` 在构造客户端时会先引导平台证书，失败即抛 `No wechatpay platform certificate`
> —— 支付相关接口会全部 5xx。配上 `WX_PAY_PUBLIC_KEY_PATH` + `WX_PAY_PUBLIC_KEY_ID` 后 SDK
> 跳过该引导、改用公钥验签（`Wechatpay-Serial` 按公钥 ID 匹配）。缺少任一项时代码会打印
> `WeChat Pay public key ... is not configured` 警告并退回旧行为。

注意事项：

- `WX_PAY_ENABLED=false` 的行为是**直接把订单标记为已支付且不产生任何交易**（等于免费订场），仅用于本地开发与 CI。生产必须 `true`。
- 启动日志会打印 `booking payment: wechat pay client ready (verify mode=public_key)`；若打印
  `WECHAT PAY CLIENT INIT FAILED` 说明商户参数（尤其公钥）不完整，此时下单接口会 5xx。
- **`WX_PAY_NOTIFY_URL` 走 8443**：微信商户平台配「支付回调域名」时会校验 443 与备案，但**下单接口的 `notify_url` 参数不看那个配置**。备案完成后把它换回 443 是不带端口的地址即可，无需改代码与 nginx。
- 私钥路径用 `/app/pay-certs/` 而不是 `/app/certs/`：`compose.production.yml` 把 `WX_PAY_CERT_DIR` 固定为 `/app/pay-certs`，而 `backend/certs` 是 `read_only` 挂载。公钥模式下该目录只用来放 `apiclient_key.pem` / `pub_key.pem`，SDK 不再写平台证书。
- `backend/pay-certs/` 已被 `.gitignore` 忽略，且 compose 用的是 `create_host_path: false` —— **宿主机上该目录必须已存在**（2026-10-13 已创建，`root:root 700`），否则容器会拒绝启动，部署预检 `scripts/validate-production.py` 也会直接失败。
- 私钥与公钥权限建议 `chmod 600`，属主 root（容器内进程以 root 运行）。

## 三、代码侧改动（本次已完成）

| 文件 | 改动 |
|---|---|
| `backend/app/api/v1/bookings.py` | `pay_booking`：`WX_PAY_ENABLED=true` 时走 `_wx_prepay()` 真实 JSAPI 统一下单并返回 `pay_params`；`false` 时保留占位（仅开发/CI）。复用 5 分钟内的 `prepay_id`；付款成功**只由 `/wx-notify` 回调或 `/sync-payment` 查单**改状态，接口自身不标 paid |
| `backend/app/api/v1/bookings.py` | **新增 `POST /{booking_id}/sync-payment`**：主动查单兜底。校验归属与状态后调 `wxpay.query(out_trade_no=...)`，`trade_state=SUCCESS` 时复用 `_handle_payment_success` 落库；非 pending 直接回报（幂等）；占位模式不查单 |
| `backend/app/api/v1/bookings.py` | **新增 `POST /{booking_id}/sync-refund`**：退款主动查单兜底。权限为「订单本人 / 平台管理员 / 本俱乐部管理员」；调 `wxpay.query_refund(out_refund_no=order.refund_id)`，命中终态时把 `status` 映射成回调格式后复用 `_handle_refund_callback` 落库；单号不匹配一律 502 拒绝落库（防错单）；占位模式与已终态直接回报 |
| `backend/app/core/wechat_pay.py` | **新增 `wx_request()` + `WeChatPayError`**：该 SDK 的 `core.request` **一律**返回 `(http_status, text)` 元组，调用方极易误当 dict 用（见第 7 节）。所有调用统一经此解包 |
| `backend/app/core/wechat_pay.py` | **新增 `_load_pay_public_key()` 与公钥模式**：配置 `WX_PAY_PUBLIC_KEY_PATH` + `WX_PAY_PUBLIC_KEY_ID` 时把公钥透传给 SDK 并置 `cert_dir=None`，跳过已被微信下线的平台证书引导；缺项时打 warning 并退回旧行为 |
| `backend/app/core/config.py` | 新增 `WX_PAY_PUBLIC_KEY_PATH` / `WX_PAY_PUBLIC_KEY_ID`（微信支付公钥模式） |
| `backend/app/main.py` | `WX_PAY_ENABLED=true` 时启动即构造一次支付客户端并打印 `verify mode=public_key` 或 `platform_certificates`；构造失败只记 ERROR 不阻断启动，便于第一时间发现凭证问题 |
| `backend/tests/test_wechat_pay_client.py` | 公钥模式契约测试：只配一半视为未配置、配全后 `cert_dir=None` 且透传公钥、未配时退回 `cert_dir`、商户四件套缺一即拒绝构造 |
| `backend/app/api/v1/bookings.py` | `refund_booking` 改走 `wx_request`：此前 SDK 返回 4xx 时不抛异常，退款被微信拒绝也会把订单标成 `refunding`；现在会正确失败 |
| `backend/app/tasks/tasks.py` | 修 `_retry_failed_refunds_impl` / `_poll_processing_refunds_impl` 的元组解包 bug；并**区分两类失败**：查询失败保持 `refunding` 延后重试（绝不回退订单），只有微信明确拒绝提交才回退为 `paid` |
| `backend/app/tasks/tasks.py` | `_update_order_after_refund` 的 `success` 分支补设 `refund_status` / `refund_time`，与回调路径字段一致 |
| `backend/app/services/settlement.py` | 4 处分账调用（`profitsharing_order` / `_query` / `_unfreeze`）改走 `wx_request`，属同一类解包 bug，避免将来启用分账时踩雷 |
| `backend/app/core/config.py` | 新增 `WX_PAY_ENABLED`、`WX_PAY_DESCRIPTION`、`PROFIT_SHARING_ENABLED`、`RATE_LIMIT_SYNC_PAY_PER_MINUTE`（30/分钟，查单比下单频繁，需独立限额）、`RATE_LIMIT_SYNC_REFUND_PER_MINUTE`（同样 30/分钟） |
| `backend/app/tasks/tasks.py` | `execute_pending_settlements` 在 `PROFIT_SHARING_ENABLED=false` 时跳过，不再向微信发起分账 |
| `backend/app/main.py` | 启动打印支付开关与分账开关状态 |
| `scripts/validate-production.py` | `WX_MCH_*` / `WX_PAY_NOTIFY_URL` / `WX_PAY_PUBLIC_KEY_*` 加入生产变更白名单；支付开关本身**不**入白名单，其值一旦被改动会被预检拦下要求人工确认 |
| `frontend/src/services/payment.ts` | `payBooking()` 调起收银台、区分「用户取消」与「支付失败」；新增 `syncBookingPayment()` / `confirmBookingPaid()` |
| `frontend/src/pages/booking/confirm.vue` | 调起真实支付；支付返回后主动查单确认；取消支付保留订单便于重试 |
| `frontend/src/pages/booking/success.vue` | 结果页原有 3 秒轮询顺带触发查单，回调不通时也能自动转成「支付成功」 |
| `frontend/src/pages/profile/my-bookings.vue` | 待支付订单可支付、可「刷新状态」（手动触发查单）；**退款中**订单可「刷新退款」 |
| `frontend/src/pages/admin/order-manage.vue` | 管理端「退款中」订单可「刷新退款」，即时确认退款结果 |
| `backend/tests/test_booking_placeholder.py` | 支付契约测试：开关**关闭**时占位确认且绝不触碰微信接口；开关**打开**时返回 `pay_params`、订单保持 `pending`、时段锁不释放（等回调） |
| `backend/tests/test_payment_sync.py` | 主动查单契约测试（支付 + 退款）：占位模式不查单、终态幂等、越权 403、错单防护、命中终态落库 |
| `backend/tests/test_refund_sync_task.py` | 退款定时任务回归测试：正确解析 SDK 元组响应、查询失败不回退订单、4xx 时重新提交 |

## 四、上线步骤

商户号已开通后，顺序是：**商户平台取值 → 服务器写配置 → 推 master → 小额真单验收**。

### 第 0 步：商户平台（拿 5 个值 + 配 1 个域名）

| 事项 | 入口 | 拿到什么 |
|---|---|---|
| 开通 **JSAPI 支付** | 产品中心 → JSAPI支付 → 申请开通 | 小程序支付权限（审核约 7 个工作日） |
| 关联小程序 AppID | 产品中心 → AppID账号管理 | 填 `wxe6fd99528373b676`，关联后回**小程序后台点「确认」** |
| 设置 **APIv3 密钥** | 账户中心 → API安全 | 自定义 32 位字符串，**务必留存**；后续改动会导致回调 AES 解密全部失败 |
| 申请**商户 API 证书** | 账户中心 → API安全 | 下载 `apiclient_key.pem` + 记下**证书序列号**（`openssl x509 -in apiclient_cert.pem -noout -serial`） |
| 申请**微信支付公钥** | 账户中心 → API安全 → 微信支付公钥 | 下载 `pub_key.pem` + 公钥 ID `PUB_KEY_ID_...`。**必需**：微信已下线平台证书 |
| 配置**支付回调域名** | 产品中心 → 开发配置 | `www.tennisplaynow.site`（**不带协议、端口、路径**） |

### 第 1 步：服务器写配置

```bash
cd /home/ubuntu/playnow-miniapp
sudo cp -p backend/.env backend/.env.bak.$(date +%Y%m%d%H%M%S)
sudo mkdir -p backend/pay-certs && sudo chmod 700 backend/pay-certs
# 上传两把密钥到 backend/pay-certs/ 后 chmod 600：
#   apiclient_key.pem  商户 API 私钥（证书包里的）
#   pub_key.pem        微信支付公钥（API安全页下载的）
sudo vim backend/.env   # 按上面「服务器配置」填写，含 WX_PAY_ENABLED=true 与两个公钥变量
sudo docker compose -f compose.production.yml --env-file .env.production up -d
```

> 该目录 2026-10-13 已建好（`root:root 700`），`apiclient_key.pem` 已就位；缺的只有 `pub_key.pem`。

### 第 2 步：本地推 master 触发部署（PR 不部署）

```bash
git push origin master
```

> ⚠️ 部署预检 `scripts/validate-production.py` 会拦「生产配置变化」：它拿 `docker inspect club-api` 的**当前运行容器环境变量**作为基准，遍历旧键、发现新值与旧值不同且不在白名单内就中止部署。
>
> - `WX_MCH_*` / `WX_PAY_NOTIFY_URL` / `WX_PAY_PUBLIC_KEY_*` **已在白名单内**，可直接过
> - `WX_PAY_ENABLED` 故意**不在**白名单（`false` 等于免费订场，任何改动都应人工确认）
> - **但本次不会触发**：2026-10-13 实测线上 `club-api` 容器只有 `WX_APP_ID` / `WX_APP_SECRET` / `WX_PAY_CERT_DIR`，**没有 `WX_PAY_ENABLED` 这个键** —— 遍历不到它，直接通过，**不需要临时改 `changed_keys`**
> - 只有等它上线之后再被改动，才会被拦下要求人工确认，这是设计意图

### 第 3 步：确认启动日志

```bash
docker logs club-api --since 5m 2>&1 | grep -E "booking payment|profit sharing|media storage"
# 期望：booking payment: wechat pay enabled
#       profit sharing: disabled
#       media storage backend: cos
```

## 五、验收自查

| 检查项 | 期望结果 |
|---|---|
| 下单接口 | 返回 `pay_params`（含 `paySign`），订单仍为 `pending` |
| 支付页取消 | 前端提示「已取消支付」，订单不变成 `paid` |
| 完成支付 | 订单变 `paid`，`wx_transaction_id` 是微信 32 位单号（**不是** `dev_` 开头的假单号） |
| **主动查单** | 支付后在「我的预约」点**刷新状态**，或停在支付结果页等轮询 —— 回调不通时也能把订单同步为 `paid`（这是当前**主要**的确认手段） |
| **回调地址** | `WX_PAY_NOTIFY_URL` 指向 `:8443`；备案完成后换回 443 不带端口的地址 |
| 商户平台 | 「交易中心」能看到该笔订单，金额与订单一致 |
| 回调 | 后端日志无 `Callback verify/decrypt failed`；若 8443 被微信拒收，日志也无异常（由查单兜底） |
| 退款 | `POST /bookings/{id}/refund` 后商户平台出现退款单 |
| **退款主动查单** | 对 `refunding` 订单点「刷新退款」→ 微信已退成功时立即转为 `refunded` 并释放时段 |
| **退款定时兜底** | 什么都不点时，退款结果也会在 ≤5 分钟内被 Celery 自动同步；日志无 `Refund query failed` / `Poll failed` |
| 退款被拒 | 微信因余额/参数等原因拒绝退款时，订单**不会**停在 `refunding`，而是回到 `paid` 且 `refund_status=failed` |

APIv3 **没有官方沙箱环境**（沙箱仅 v2 提供），建议用最低金额的真实订单先跑通一笔。

## 六、明确的技术债与风险

1. **二清风险**：平台收全款再与俱乐部结算，属于资金归集；如有监管要求，需改为服务商模式（俱乐部作为特约商户自己收款，平台分账抽佣）。
2. **分账上限**：微信分账单笔默认上限 30%，且要求的 `settle_info.profit_sharing=true` 一旦漏传，该订单**永久无法分账且不可补**。当前统一传 `false`（平台直收不分账）。
3. **历史假数据**：`WX_PAY_ENABLED=false` 期间产生的 `dev_` 交易号订单不涉及真实资金，如需清理请先确认是否影响退款流程。
4. **回调链路受备案制约（当前最大外部依赖）**：域名未完成 ICP 备案时，腾讯云拦截 80/443，微信回调从公网到不了 443。当前靠 ①`notify_url` 走 8443 + ②主动查单兜底 维持闭环。**风险点**：
   - 微信若对非标准端口静默丢弃回调，则只有查单兜底在工作 —— 用户需停留在结果页几秒或手动刷新，主动性略降
   - 退款结果的回调（`REFUND.*`）同样走 8443，也受同一制约 —— **已补齐三层兜底**（见上文退款链路小节的 4b 与第 3 节），不再依赖回调
5. ~~退款缺少主动查单兜底~~ → **已补齐**（`POST /bookings/{id}/sync-refund` + 前端「刷新退款」入口）。此外排查时发现退款兜底此前因 SDK 返回值解包 bug 而**完全静默失效**，已一并修复，详见第 7 节。

## 七、SDK 返回值解包 bug（本次修复，重要）

`wechatpayv3` 的 `core.request()` **无一例外**返回 `(http_status, text)` 元组：

```python
# wechatpayv3/core.py:172
return response.status_code, response.text if 'application/json' in ... else response.content
```

但 `tasks.py` 与 `settlement.py` 里把它们当成 dict 直接 `.get()`，于是：

| 位置 | 后果 |
|---|---|
| `tasks.py::_retry_failed_refunds_impl` 查退款状态 | `AttributeError: 'tuple' object has no attribute 'get'` → 被 `except` 吞掉 → **退款兜底彻底失效** |
| 同函数的异常分支 | 不可重试异常会执行 `_update_order_after_refund(..., "failed")` → 把订单从 `refunding` **回退成 `paid`**，而款项其实已退成功 → 资金与状态不一致 |
| `tasks.py::_poll_processing_refunds_impl` | 同上；且未知状态也会把订单标 `failed` |
| `bookings.py::refund_booking` | SDK 返回 4xx 时不抛异常 → 退款被微信拒绝，订单仍被标成 `refunding` |
| `settlement.py` 4 处分账调用 | 分账一旦启用即报错（当前 `PROFIT_SHARING_ENABLED=false`，尚未暴露） |

**修复方式**：`app/core/wechat_pay.py` 新增 `wx_request(wxpay, method, **kwargs)` 统一解包为 dict，非 2xx 抛 `WeChatPayError`；所有调用点改用它。同时把「查询失败」与「提交被拒」分开处理，**查询失败绝不再回退订单**。

`tests/test_refund_sync_task.py` 用 7 个用例锁定这些行为（含「元组响应能正确落库」「查询失败不回退订单」两条回归）。
