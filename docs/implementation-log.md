# PlayNow 网球专项重构实现记录

## 版本历史

### v1.0.3 (2026-06-11)
- 用户资料页 NTRP 等级显示与编辑
- 头像上传功能

### v1.0.2 (2026-06-11)
- 帖子列表按距离排序（Haversine 公式）
- 首页「最新发布/距离最近」切换
- 帖子卡片显示距离

### v1.0.1 (2026-06-11)
- 修复上传脚本 Node 版本问题

### v1.0.0 (2026-06-11)
- NTRP 等级体系（1.0-7.0）
- 场馆图片上传（创建俱乐部时，最多9张）
- PDF 文件上传（场地规则，最多5个，每个10MB）
- 地图 API 选址（wx.chooseLocation）
- 约球帖详情页（场馆封面图、PDF预览、地图导航）

---

## 1. NTRP 等级体系

### 前端
- `miniprogram/pages/publish/post-create.js` - levels 数组改为 NTRP 等级
- `miniprogram/pages/publish/post-create.wxml` - picker 标签改为「NTRP 等级」
- `miniprogram/pages/home/index.wxml` - 显示改为 `NTRP {{level}}`
- `miniprogram/pages/profile/index.wxml` - 资料页显示 NTRP 徽章
- `miniprogram/pages/profile/edit.js` / `edit.wxml` - 编辑页支持修改 NTRP

### 后端
- `backend/app/models/models.py` - User 表添加 `ntrp_level` DECIMAL(2,1)
- `backend/app/schemas/schemas.py` - UserUpdate / UserMeResponse 添加 ntrp_level
- `backend/app/api/v1/users.py` - /users/me 返回 ntrp_level，PUT 支持更新

### NTRP 等级说明
| 等级 | 水平 |
|------|------|
| 1.0-1.5 | 初学者 |
| 2.0-2.5 | 初级 |
| 3.0-3.5 | 中级 |
| 4.0-4.5 | 中高级 |
| 5.0-5.5 | 高级 |
| 6.0-7.0 | 专业/职业 |

---

## 2. 场馆图片上传

### 规则
- 在创建俱乐部时上传，不是在发布约球帖时
- 最多 9 张图片
- 第一张自动设为封面图

### 前端
- `miniprogram/pages/publish/club-create.wxml` - 图片上传网格
- `miniprogram/pages/publish/club-create.js` - chooseImage / previewImage / removeImage / uploadImages
- `miniprogram/app.js` - 添加全局 uploadFile() 方法

### 后端
- `backend/app/api/v1/clubs.py` - 创建时接收 images 数组，第一张设为 cover_image
- `backend/app/schemas/schemas.py` - ClubCreate 添加 images 字段

---

## 3. PDF 文件上传

### 规则
- 俱乐部可上传 PDF（场地规则、价目表等）
- 最多 5 个文件，每个 10MB
- 存储在 OSS

### 前端
- `miniprogram/pages/publish/club-create.wxml` - PDF 列表和上传按钮
- `miniprogram/pages/publish/club-create.js` - chooseDocument / removeDocument / uploadDocuments
- `miniprogram/pages/common/post-detail.wxml` - 「场地规则」卡片
- `miniprogram/pages/common/post-detail.js` - onOpenDocument 用 wx.openDocument 预览

### 后端
- `backend/app/models/models.py` - Club 表添加 documents JSON 字段
- `backend/app/schemas/schemas.py` - ClubCreate/ClubUpdate/ClubDetail 添加 documents
- `backend/app/api/v1/clubs.py` - 创建/返回俱乐部时处理 documents
- `backend/app/api/v1/posts.py` - 帖子详情返回 club_documents

---

## 4. 地图 API 选址

### 规则
- 禁止手动输入地址，必须通过地图选择
- 使用微信小程序 wx.chooseLocation
- 选择后自动填充名称、地址、经纬度

### 前端
- `miniprogram/pages/publish/club-create.wxml` - 地址点击区域
- `miniprogram/pages/publish/club-create.js` - chooseLocation()
- `miniprogram/pages/common/post-detail.js` - 点击地址 wx.openLocation 导航

### 后端
- `backend/app/schemas/schemas.py` - ClubCreate 确保 latitude/longitude
- `backend/app/api/v1/clubs.py` - 保存经纬度

---

## 5. 约球帖详情页

### 结构
1. 顶部场馆封面图
2. 标题 + 标签行
3. 信息列表（发起人/时间/地点）
4. 价格 & 报名状态
5. 场地规则（PDF 列表）
6. 已报名用户头像
7. 底部操作栏（群聊/分享/报名）

### 文件
- `miniprogram/pages/common/post-detail.wxml`
- `miniprogram/pages/common/post-detail.wxss`
- `miniprogram/pages/common/post-detail.js`
- `backend/app/api/v1/posts.py` - 返回 venue_address/latitude/longitude/cover_image/club_documents
- `backend/app/schemas/schemas.py` - PostDetail 添加对应字段

---

## 6. 距离排序

### 后端
- `backend/app/api/v1/posts.py` - list_posts 支持 lat/lng/sort_by 参数
- Haversine 公式计算距离，单位 km

### 前端
- `miniprogram/pages/home/index.js` - sortBy 状态切换
- `miniprogram/pages/home/index.wxml` - 排序选项 UI
- `miniprogram/pages/home/index.wxss` - 排序按钮样式
- `miniprogram/app.js` - getUserLocation() 方法（gcj02）

---

## 7. 发布权限控制

### 规则
- 仅俱乐部成员（owner/admin）可发布约球帖
- 无俱乐部用户隐藏发布入口

### 实现
- `miniprogram/custom-tab-bar/index.js` - 根据 hasClub / isAdmin 过滤 actionSheetItems
- `backend/app/api/v1/posts.py` - create_post 检查 ClubMember 权限

---

## 8. 上传脚本

### 文件
- `scripts/upload-miniprogram.sh`

### 关键点
- 系统 Node v25 与 miniprogram-ci 不兼容
- 硬编码 Node 18 路径：`/Users/zhli22/.nvm/versions/node/v18.20.8/bin/node`
- 参数名：`--private-key-path`（不是 --pkp）

---

## 数据库变更（待执行）

```sql
-- users 表添加 ntrp_level
ALTER TABLE users ADD COLUMN ntrp_level DECIMAL(2,1) NULL COMMENT 'NTRP网球等级';

-- clubs 表添加 documents
ALTER TABLE clubs ADD COLUMN documents JSON NULL COMMENT 'PDF文件列表 [{name, url, size}]';
```

---

## 待办事项

1. [ ] `pages/profile/edit.wxss` 样式文件
2. [ ] 数据库 migration 执行
3. [ ] 报名后一键导航到场馆
4. [ ] Docker 后端部署配置
5. [ ] 后端用户注册时默认 NTRP 等级
