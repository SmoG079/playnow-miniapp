# 地理位置功能完善规范 (SSD)

## 1. 报名流程中的地理位置

### 1.1 用户授权位置
- 用户首次打开小程序时，在首页请求 `wx.getLocation` 授权
- 授权后保存用户当前位置到 `globalData.userLocation`
- 未授权时，列表按时间排序，不显示距离

### 1.2 帖子列表按距离排序
- 首页增加排序选项：「最新发布」/「距离最近」
- 选择「距离最近」时，调用后端接口传入用户经纬度
- 后端计算帖子所属俱乐部的距离，按距离升序返回

### 1.3 后端距离计算
- 使用 Haversine 公式计算两点间距离
- 在帖子列表接口支持 `lat`/`lng`/`sort_by=distance` 参数
- 返回字段增加 `distance`（单位：km，保留1位小数）

## 2. API 变更

### 2.1 帖子列表接口
```
GET /api/v1/posts?lat=39.9042&lng=116.4074&sort_by=distance&page=1

响应增加：
{
  "distance": 2.5,  // km
}
```

### 2.2 用户位置存储
- 前端：`app.globalData.userLocation = {latitude, longitude}`
- 每次打开首页时更新位置

## 3. 需要修改的文件

### 前端
- `miniprogram/app.js` - 添加 `getUserLocation()` 方法
- `miniprogram/pages/home/index.js` - 排序切换逻辑，传入位置参数
- `miniprogram/pages/home/index.wxml` - 排序选项 UI
- `miniprogram/pages/common/post-detail.js` - 报名前检查位置授权（用于导航）

### 后端
- `backend/app/api/v1/posts.py` - 帖子列表支持距离排序
- `backend/app/schemas/schemas.py` - `PostBrief` 添加 `distance` 字段

## 4. 交互流程

1. 用户打开首页 → 请求位置授权
2. 授权成功 → 保存位置 → 默认按「最新发布」排序
3. 用户点击「距离最近」→ 调用接口传入位置 → 列表按距离排序
4. 每个帖子卡片显示距离标签（如「2.5km」）
5. 用户点击帖子 → 详情页显示完整地址 → 点击导航
6. 报名成功后 → 可一键导航到场馆
