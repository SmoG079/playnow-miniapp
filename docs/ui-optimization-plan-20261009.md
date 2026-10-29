# 前端优化修改计划（2026-10-09）

> 背景：本轮 4 项优化（轮询 / 订场页性能 / UI 协调性 / 开发者工具验证）已完成一轮实现，
> 但构建产物在微信开发者工具中编译失败（uni build 本身全绿），**已全部回退**。
> 仅保留 pages.json 的下拉刷新配置修复（该改动在 16:05 的构建+截图中已验证通过）。

## 0. 事故记录与教训

- 16:05 构建 + 12 页截图全部成功 → 之后应用 8 个文件的改动 → 开发者工具编译失败（automator 命令全部超时）。
- 排除项：`:active` 伪类（删除后仍失败）；pages.json（首轮已验证）。
- 嫌疑排序（未定案）：
  1. `post-create.vue` 模板重写 —— 它是 **tabBar 页面，小程序启动即加载**，它的 WXML 编译失败会拖垮整个 app；
  2. `my-activities.vue` 模板结构调整（phase-wrap 包裹 scroll-view）；
  3. 其余纯 script 改动理论上不影响编译，但不能排除。
- **教训：改动必须分批应用，每批构建后在开发者工具里验证编译，再进下一批。**

## 1. 批次一：轮询优化（纯 script，风险最低，先做）

现状：tournament-detail 与 my-activities 均为 5 秒 setInterval 整页刷新。

| 文件 | 改法 |
|---|---|
| `pages/common/tournament-detail.vue` | 固定 5s → 自适应 setTimeout 链：存在未完场次（status=pending 且有双方队伍）10s；报名中/进行中 20s；已结束/取消/关闭 **停止轮询**。onHide/onUnload 清理逻辑不变 |
| `pages/profile/my-activities.vue` | 固定 5s → 自适应：列表中存在待审核/候补/待支付/待核验项或进行中活动 15s，否则 45s；setInterval 改 setTimeout 链，每轮按最新 items 重新评估 |

预期收益：空闲状态请求量下降 6～9 倍，比赛日保持近实时。

## 2. 批次二：订场页加载性能（纯 script）

| 文件 | 问题 | 改法 |
|---|---|---|
| `pages/booking/club-list.vue` | 每次 onShow（含从场馆详情返回）都整页重载 | 增加 2 分钟 TTL 缓存：城市/关键词/排序签名未变且未过期时直接用现有列表 |
| `pages/booking/venue-detail.vue` | 切日期把 club 信息一起重新请求；club 未返回前整页空白 | club 只在 onLoad 拉一次；时段表按日期独立拉取；两个请求并行发出、渐进渲染 |

## 3. 批次三：图标修复（改动最小）

- `pages/profile/index.vue`："分账记录" 的 `money-circle` **不是合法 wd-icon 名**（已对照 iconfont.scss 全量清单确认），改为 `history`。
- `pages/admin/dashboard.vue`：订单管理/场地管理补 `prefix-icon`（`list` / `location`），与"我的"页 wd-cell 风格对齐。

## 4. 批次四：错误态补全

截图发现的两个白屏问题：

| 文件 | 现象 | 改法 |
|---|---|---|
| `pages/booking/venue-detail.vue` | club 请求失败（如 id 不存在）→ 整页空白 | 加 `clubFailed` 状态：图标 + "球场信息加载失败" + 重新加载按钮 |
| `pages/common/post-detail.vue` | 加载失败无任何提示，页面空白/转圈 | 加 `postFailed` 状态 + 空态重试按钮；加载中显示 wd-loading |

## 5. 批次五：UI 重构（改动最大，最后单独验证）

### 5.1 发布页卡片化（核心，截图确认"过于简单"）
现状：两个纯文字标题 + 文字按钮链接 + 底部孤立的"创建俱乐部"，无卡片/图标/视觉层级。
改法：三个横向图标卡片（对齐全 app 白卡 + 16px 圆角 + 1px 描边风格）：
- 发布约球：`user-group` 图标 + "日常约球" tag + 描述 + 右箭头
- 发布比赛：`trophy` 图标 + "正式比赛" tag + 描述 + 右箭头（未登录显示 permission-note）
- 创建俱乐部：`company` 图标 + 描述 + 右箭头
所有图标名已对照 `wd-icon` iconfont 清单验证存在。

### 5.2 我的活动筛选行渐隐
现状：phase 横向滚动区被右侧"筛选·比赛"挤压，"已结束"截断处无滚动暗示。
改法：滚动区外包 `.phase-wrap`（flex:1 + position:relative），右缘 18px 渐变遮罩提示可滚动。

## 6. 每批次统一验证流程（可自动化）

```bash
npm run build:mp-weixin          # uni 编译
cli quit && cli auto --project frontend/dist/build/mp-weixin --auto-port 9420
# automator: systemInfo() 健康检查 + 目标页面截图
```

- `systemInfo()` 超时 = 编译失败，立即 bisect 当前批次的文件。
- 批次五涉及模板重写，建议先只改 post-create.vue 验证，再加 my-activities。

## 7. 已确认无需改动的项

- 色板一致性：全量扫描仅 6 处暖色强调（未读红点 #e24b4a、琥珀警示），均为功能性用色，不冲突。
- 定时器清理、v-for :key、tabBar 跳转、登录回跳：上轮审查已确认规范。
- 后端 `/bookings/{id}/pay` 仍为占位实现（直接标记已支付），接真实微信支付时前端需同步改造 confirm.vue。
