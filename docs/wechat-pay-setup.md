# 微信支付接入：平台直收模式

> 2026-10-13：本接入方案已暂缓。当前订场使用占位确认，真实预支付及前端收银台调用已注释；下文是后续恢复方案，不代表当前线上收款行为。恢复前须完成支付与退款验收，参见 [预订支付待办](deferred-booking-payments.md)。

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
| 6 | 回调置订单 `paid`、时段转 `booked`、发通知 | `services/payment_callback.py` |
| 7 | T+1 自动结算到平台结算账户（对公户或经营者个人卡） | 微信 |

订单状态**只由回调置为已支付**，`/pay` 接口自己绝不标 `paid`。

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
| 6 | **商户 API 证书** | 账户中心 → API安全 | 得到 `apiclient_key.pem` + **证书序列号** |
| 7 | **支付回调域名** | 产品中心 → 开发配置 | 填 `www.tennisplaynow.site`，**不带协议/端口/路径** |

### C. 服务器与域名

| # | 事项 | 说明 |
|---|---|---|
| 1 | `www.tennisplaynow.site` 完成 **ICP 备案** | 微信配置合法域名与回调域名时都会校验；腾讯云 CDN 报 `CdnHostNoIcp` 说明此前未打通 |
| 2 | Nginx 在 **443** 上反代 `/api/v1/bookings/wx-notify` → `127.0.0.1:8000` | 微信要求回调域名**不能带端口**，8443 不行 |
| 3 | 私钥放到 `backend/pay-certs/apiclient_key.pem` | 该目录由 compose 挂载到容器 `/app/pay-certs` |

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

因此：

- **不需要牌匾、门面、收银台照片**，也不存在"必须到店拍"的要求 —— 那些都只针对线下场景
- 真正的替代物是**小程序页面截图**（≤5 张、每张 ≤2M），建议顺序：首页 → 场地列表 → 场地详情 → 下单确认页 → 订单/我的预订页
- 如果小程序**尚未发布上线**，这一步**必须**提交截图或设计稿
- 入驻时填的 AppID 会**自动发起商户号与该 AppID 的授权绑定**，之后去小程序后台点「确认」即可（对应 A 表第 4 项）

**商户简称命名规则（个体户）**：不支持单纯用人名，可用「个体户 + 经营者名称」或「经营者名称 + 业务」命名，如"张三网球"；不支持"XX特约商户""800"这类无意义文案。该简称会直接显示在用户支付凭证上。

⚠️ **别为了"好过审"去选线下场所**：线下场景会进入后续的「经营场景检查」（监管要求到店实地拍摄、不支持相册上传，每次审核 3–7 个工作日）。纯线上业务选了线下，等于给自己埋一个长期的合规雷。

## 二、服务器配置

编辑 `/home/ubuntu/playnow-miniapp/backend/.env`（先备份）：

```ini
WX_MCH_ID=1900000000
WX_MCH_API_V3_KEY=<32位APIv3密钥>
WX_MCH_SERIAL_NO=<证书序列号>
WX_MCH_PRIVATE_KEY_PATH=/app/pay-certs/apiclient_key.pem
WX_PAY_CERT_DIR=/app/pay-certs
WX_PAY_NOTIFY_URL=https://www.tennisplaynow.site/api/v1/bookings/wx-notify
WX_PAY_ENABLED=true
WX_PAY_DESCRIPTION=网球场地预订
PROFIT_SHARING_ENABLED=false
```

注意事项：

- `WX_PAY_ENABLED=false` 的行为是**直接把订单标记为已支付且不产生任何交易**（等于免费订场），仅用于本地开发与 CI。生产必须 `true`。
- 私钥路径用 `/app/pay-certs/` 而不是 `/app/certs/`：`compose.production.yml` 把 `WX_PAY_CERT_DIR` 固定为 `/app/pay-certs`，而 `backend/certs` 是 `read_only` 挂载，SDK 下载平台证书时写不进去。
- `backend/pay-certs/` 已被 `.gitignore` 忽略，且 compose 用的是 `create_host_path: false` —— **宿主机上该目录必须已存在**，否则容器会拒绝启动，部署预检 `scripts/validate-production.py` 也会直接失败。
- 私钥权限建议 `chmod 600`，属主为部署用户。

## 三、代码侧改动（本次已完成）

| 文件 | 改动 |
|---|---|
| `backend/app/api/v1/bookings.py` | `pay_booking` 由占位改为真实 JSAPI 统一下单；新增 `_wx_prepay()`；复用 5 分钟内的 `prepay_id`；补支付限流；`WX_PAY_ENABLED=false` 时保留本地兜底（仅开发/CI） |
| `backend/app/core/config.py` | 新增 `WX_PAY_ENABLED`、`WX_PAY_DESCRIPTION`、`PROFIT_SHARING_ENABLED` |
| `backend/app/tasks/tasks.py` | `execute_pending_settlements` 在 `PROFIT_SHARING_ENABLED=false` 时跳过，不再向微信发起分账 |
| `backend/app/main.py` | 启动打印支付开关与分账开关状态 |
| `scripts/validate-production.py` | `WX_MCH_*` / `WX_PAY_NOTIFY_URL` 加入生产变更白名单；支付开关本身**不**入白名单，任何改动都会被预检拦下 |
| `frontend/src/services/payment.ts` | 新增 `payBooking()`；区分「用户取消」与「支付失败」 |
| `frontend/src/pages/booking/confirm.vue` | 调起真实支付；取消支付保留订单便于重试 |
| `frontend/src/pages/profile/my-bookings.vue` | 待支付订单同样调起真实支付 |

## 四、上线步骤

```bash
# 1. 服务器：备份并写入配置
cd /home/ubuntu/playnow-miniapp
cp backend/.env backend/.env.bak.$(date +%Y%m%d%H%M%S)
mkdir -p backend/pay-certs && chmod 700 backend/pay-certs
# 上传 apiclient_key.pem 到 backend/pay-certs/ 后 chmod 600
vim backend/.env   # 按上面「服务器配置」填写

# 2. 本地：提交并推 master 触发部署（PR 不部署）
git push origin master
```

部署成功后在服务器确认：

```bash
docker logs club-api --since 5m 2>&1 | grep -E "wechat pay|profit sharing|media storage"
# 期望：wechat pay: enabled (notify_url=https://www.tennisplaynow.site/api/v1/bookings/wx-notify)
```

## 五、验收自查

| 检查项 | 期望结果 |
|---|---|
| 下单接口 | 返回 `pay_params`（含 `paySign`），订单仍为 `pending` |
| 支付页取消 | 前端提示「已取消支付」，订单不变成 `paid` |
| 完成支付 | 订单变 `paid`，`wx_transaction_id` 是微信 32 位单号（**不是** `dev_` 开头的假单号） |
| 商户平台 | 「交易中心」能看到该笔订单，金额与订单一致 |
| 回调 | 后端日志无 `Callback verify/decrypt failed` |
| 退款 | `POST /bookings/{id}/refund` 后商户平台出现退款单 |

APIv3 **没有官方沙箱环境**（沙箱仅 v2 提供），建议用最低金额的真实订单先跑通一笔。

## 六、明确的技术债与风险

1. **二清风险**：平台收全款再与俱乐部结算，属于资金归集；如有监管要求，需改为服务商模式（俱乐部作为特约商户自己收款，平台分账抽佣）。
2. **分账上限**：微信分账单笔默认上限 30%，且要求的 `settle_info.profit_sharing=true` 一旦漏传，该订单**永久无法分账且不可补**。当前统一传 `false`（平台直收不分账）。
3. **历史假数据**：`WX_PAY_ENABLED=false` 期间产生的 `dev_` 交易号订单不涉及真实资金，如需清理请先确认是否影响退款流程。
