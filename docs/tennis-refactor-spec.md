# PlayNow 网球专项重构规范 (SSD)

## 背景
PlayNow 从通用运动平台转型为网球专项服务平台。本次重构涉及用户等级体系、场馆管理、地址选择等核心功能。

---

## 1. 用户等级体系：NTRP 等级

### 1.1 规则
- 采用美国网球协会（USTA）NTRP（National Tennis Rating Program）等级标准
- 等级范围：1.0 - 7.0，步进 0.5
- 等级说明：
  - 1.0-1.5：初学者，刚接触网球
  - 2.0-2.5：初级，能进行简单对打
  - 3.0-3.5：中级，能稳定对打，掌握基本战术
  - 4.0-4.5：中高级，有较强比赛能力
  - 5.0-5.5：高级，半专业/专业选手
  - 6.0-7.0：专业/职业球员

### 1.2 需要修改的文件

#### 前端
- `miniprogram/pages/publish/post-create.js`
  - `levels` 数组改为 NTRP 等级：`['不限', '1.0', '1.5', '2.0', '2.5', '3.0', '3.5', '4.0', '4.5', '5.0', '5.5', '6.0', '6.5', '7.0']`
  - `levelIndex` 默认值保持 -1（不限）

- `miniprogram/pages/publish/post-create.wxml`
  - picker 显示文字改为 "NTRP 等级"

- `miniprogram/pages/home/index.wxml`
  - 水平显示改为 "NTRP {level}"

- `miniprogram/pages/profile/index.js` / `index.wxml`
  - 用户资料页添加 NTRP 等级设置/显示

#### 后端
- `backend/app/schemas/schemas.py`
  - `level_required` 字段验证：可选值或 null，格式为 "X.X" 或 "不限"

- `backend/app/models/models.py`
  - `User` 表添加 `ntrp_level` 字段（DECIMAL(2,1)，nullable）

- `backend/app/api/v1/users.py`
  - 添加更新 NTRP 等级接口

---

## 2. 场馆图片：创建时上传

### 2.1 规则
- 场馆图片在**创建场馆/俱乐部时**上传，不是在发布约球帖时
- 支持多张图片（最多 9 张）
- 第一张为封面图
- 约球帖详情页显示场馆封面图

### 2.2 需要修改的文件

#### 前端
- `miniprogram/pages/publish/club-create.wxml`
  - 添加图片上传区域（参考微信小程序 `wx.chooseMedia`）
  - 支持预览和删除

- `miniprogram/pages/publish/club-create.js`
  - 添加图片选择、上传、预览、删除逻辑
  - 提交时先上传图片到 OSS，再提交表单

- `miniprogram/pages/common/post-detail.wxml`
  - 顶部图片从 `post.venue_cover_image` 或 `post.club_cover_image` 读取

#### 后端
- `backend/app/api/v1/clubs.py`
  - `POST /clubs` 接口接收 `images` 数组（OSS URL 列表）
  - 第一张图片设为 `cover_image`

- `backend/app/models/models.py`
  - `Club` 表已有 `images` (JSON) 和 `cover_image` 字段，无需修改

- `backend/app/schemas/schemas.py`
  - `ClubCreate` schema 添加 `images: List[str]` 字段

---

## 3. 场馆支持 PDF 文件上传

### 3.1 规则
- 俱乐部/场馆可上传 PDF 文件（如场地规则、价目表、会员须知）
- 最多上传 5 个 PDF 文件
- 每个文件最大 10MB
- 文件存储在 OSS
- 约球帖详情页显示 "场地规则" 入口，点击可预览/下载

### 3.2 需要修改的文件

#### 前端
- `miniprogram/pages/publish/club-create.wxml`
  - 添加 PDF 上传区域（使用 `wx.chooseMessageFile`）
  - 显示已上传文件列表（文件名 + 删除按钮）

- `miniprogram/pages/publish/club-create.js`
  - 添加 PDF 选择、上传逻辑
  - 限制文件类型为 PDF，大小 10MB

- `miniprogram/pages/common/post-detail.wxml`
  - 添加 "场地规则" 卡片，显示 PDF 文件列表
  - 点击用 `wx.openDocument` 预览

#### 后端
- `backend/app/models/models.py`
  - `Club` 表添加 `documents` 字段（JSON，存储 `{name, url, size}` 数组）

- `backend/app/schemas/schemas.py`
  - `ClubCreate` / `ClubUpdate` schema 添加 `documents` 字段
  - `ClubOut` schema 添加 `documents` 字段

- `backend/app/api/v1/clubs.py`
  - 创建/更新俱乐部时处理 `documents` 字段

---

## 4. 地址接入地图 API 选择

### 4.1 规则
- 禁止手动输入地址，必须通过地图选择
- 使用微信小程序 `wx.chooseLocation` API
- 选择后自动填充：名称、地址、纬度、经度
- 详情页点击地址可打开地图导航

### 4.2 需要修改的文件

#### 前端
- `miniprogram/pages/publish/club-create.wxml`
  - 地址输入框改为点击区域
  - 显示当前选择的地址名称和详细地址
  - 右侧添加地图图标

- `miniprogram/pages/publish/club-create.js`
  - 点击地址区域调用 `wx.chooseLocation`
  - 成功后保存 `name`, `address`, `latitude`, `longitude`
  - 提交时一并发送给后端

- `miniprogram/pages/common/post-detail.js`
  - 点击地址调用 `wx.openLocation` 打开地图导航

#### 后端
- `backend/app/schemas/schemas.py`
  - `ClubCreate` schema 添加 `latitude` 和 `longitude` 字段（已有，需确保必填）

- `backend/app/api/v1/clubs.py`
  - 创建俱乐部时保存经纬度

---

## 5. 约球帖发布权限

### 5.1 规则
- 仅俱乐部成员（owner/admin）可发布约球帖
- 无俱乐部用户隐藏发布入口
- 发布时选择所属俱乐部（如果用户属于多个俱乐部）

### 5.2 需要修改的文件

#### 前端
- `miniprogram/custom-tab-bar/index.js`
  - `onPlusTap` 中检查用户是否有俱乐部
  - 无俱乐部：提示"您需要先创建或加入俱乐部"
  - 有俱乐部：显示 action sheet，选择发布类型

- `miniprogram/pages/publish/post-create.js`
  - 页面加载时获取用户俱乐部列表
  - 如果只有一个俱乐部，自动选中
  - 如果有多个，显示 picker 选择
  - 提交时携带 `club_id`

#### 后端
- `backend/app/api/v1/posts.py`
  - `POST /posts` 检查用户是否为俱乐部成员
  - 非成员返回 403

---

## 6. 数据库变更

### 6.1 新增字段
```sql
-- users 表添加 ntrp_level
ALTER TABLE users ADD COLUMN ntrp_level DECIMAL(2,1) NULL COMMENT 'NTRP网球等级';

-- clubs 表添加 documents
ALTER TABLE clubs ADD COLUMN documents JSON NULL COMMENT 'PDF文件列表 [{name, url, size}]';
```

### 6.2 数据迁移
- 现有用户的 `level` 字段（如有）映射到 NTRP
- 现有俱乐部地址保持不变，但新创建必须通过地图选择

---

## 7. API 变更

### 7.1 创建俱乐部
```
POST /api/v1/clubs
{
  "name": "城东网球俱乐部",
  "sport_types": ["网球"],
  "description": "...",
  "address": "北京市朝阳区...",      // 从地图选择获取
  "latitude": 39.9042,              // 从地图选择获取
  "longitude": 116.4074,            // 从地图选择获取
  "contact_phone": "13800138000",
  "images": ["https://oss.../1.jpg", "https://oss.../2.jpg"],
  "documents": [
    {"name": "场地规则.pdf", "url": "https://oss.../rules.pdf", "size": 1024000}
  ]
}
```

### 7.2 创建约球帖
```
POST /api/v1/posts
{
  "club_id": 1,
  "title": "周三晚双打约球",
  "sport_type": "网球",
  "preferred_date": "2026-06-15",
  "preferred_start": "19:00",
  "preferred_end": "21:00",
  "players_needed": 4,
  "level_required": "3.5",          // NTRP 等级
  "notes": "有顶棚，满4人开赛"
}
```

### 7.3 获取约球帖详情
```
GET /api/v1/posts/{id}
响应增加字段：
{
  "venue_cover_image": "https://oss.../cover.jpg",
  "venue_address": "北京市朝阳区...",
  "venue_latitude": 39.9042,
  "venue_longitude": 116.4074,
  "club_documents": [
    {"name": "场地规则.pdf", "url": "https://oss.../rules.pdf", "size": 1024000}
  ],
  "user_phone": "13800138000"       // 发起人电话（仅报名后可见或根据隐私设置）
}
```

---

## 8. 验收标准

1. [ ] 用户可选择 NTRP 等级（1.0-7.0，步进 0.5）
2. [ ] 创建俱乐部时可上传多张场馆图片（最多9张）
3. [ ] 创建俱乐部时可上传 PDF 文件（最多5个，每个10MB）
4. [ ] 地址必须通过地图选择，禁止手动输入
5. [ ] 约球帖详情页显示场馆封面图
6. [ ] 约球帖详情页显示 "场地规则" 入口，可预览 PDF
7. [ ] 点击地址可打开地图导航
8. [ ] 无俱乐部用户隐藏发布入口
9. [ ] 仅俱乐部成员可发布约球帖
10. [ ] 所有 API 返回正确的 NTRP 等级格式
