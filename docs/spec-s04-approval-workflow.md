# S-04 约球帖报名审核流程规范

## 版本: v1.0
## 日期: 2026-06-12
## 状态: 待实现

---

## 一、当前问题诊断

### 1.1 当前实现
- `MatchPost` 无报名审核开关
- `MatchRegistration` 已有 `pending`/`approved`/`rejected` 状态
- `POST /posts/{id}/register` 直接创建 `pending` 记录
- `PUT /posts/{id}/registrations/{user_id}` 供帖主审核

### 1.2 缺失
| 缺失项 | 说明 |
|--------|------|
| 审核开关字段 | 帖主无法选择是否开启审核 |
| 审核状态感知 | 报名后用户不知道自己处于 pending |
| 独立审核 UI | 帖主只能在 post-detail 弹窗查看，无操作按钮 |
| 满员逻辑未考虑审核 | 当前满员只统计 approved，但帖主希望控制 |

---

## 二、需求规格

### 2.1 数据模型变更
`MatchPost` 增加字段：
```python
approval_required = Column(Boolean, default=False, nullable=False)
```

### 2.2 报名流程
- 当 `approval_required=True` 时：
  - 用户报名后状态为 `pending`
  - 帖主审核通过前，报名人数不计入 `registration_count` 用于满员判断
  - 帖主收到报名待审核通知
  - 报名用户收到审核结果通知
- 当 `approval_required=False` 时：
  - 用户报名后状态直接为 `approved`（与当前行为一致）
  - 达到 `players_needed` 后帖子状态变为 `full`

### 2.3 审核 API
保留并增强 `PUT /posts/{id}/registrations/{user_id}`：
- 请求：`{ "status": "approved" | "rejected" }`
- 权限：仅帖主或平台管理员
- 通过时检查是否满员，更新 `MatchPost.status`
- 拒绝时发送通知

### 2.4 发布页
`POST /posts` 和 `PUT /posts/{id}` 接受 `approval_required` 字段。

### 2.5 前端审核页面
- 新建页面：`miniprogram/pages/publish/post-registration-approve.js` / `.wxml`
- 入口：
  - post-detail 底部按钮「管理报名」跳转
  - my-posts 列表入口跳转
- 功能：
  - 显示 pending / approved / rejected 报名者列表
  - 每个 pending 报名者显示通过/拒绝按钮
  - 显示留言 message

---

## 三、API 变更

### 3.1 `MatchPost` schema
```python
class PostCreate(BaseModel):
    ...
    approval_required: bool = False

class PostUpdate(BaseModel):
    ...
    approval_required: Optional[bool] = None

class PostBrief(BaseModel):
    ...
    approval_required: bool = False

class PostDetail(PostBrief):
    ...
    approval_required: bool = False
```

### 3.2 报名接口
`POST /posts/{id}/register`
- 根据 `post.approval_required` 决定默认状态
- `approval_required=True` → `pending`
- `approval_required=False` → `approved`

### 3.3 列表与详情
- `GET /posts` 和 `GET /posts/{id}` 返回 `approval_required`
- `registration_count` 语义保持为 approved 人数（与现有逻辑一致）
- 新增 `pending_count` 到 `PostDetail` 供帖主查看待审核数量

---

## 四、数据库变更

```sql
ALTER TABLE match_posts
  ADD COLUMN approval_required TINYINT(1) NOT NULL DEFAULT 0;
```

---

## 五、需要修改的文件

### 后端
- `backend/app/models/models.py` — `MatchPost` 增加 `approval_required`
- `backend/app/schemas/schemas.py` — Post schema 增加字段
- `backend/app/api/v1/posts.py` — 创建/更新/报名/审核逻辑适配

### 前端
- `miniprogram/pages/publish/post-create.js` / `.wxml` — 增加「需要审核」开关
- `miniprogram/pages/common/post-detail.js` / `.wxml` — 显示 pending 数量，帖主跳转审核页
- `miniprogram/pages/profile/my-posts.js` / `.wxml` — 增加待审核数量角标/入口
- 新建 `miniprogram/pages/publish/post-registration-approve.js` / `.wxml` / `.json` / `.wxss`
- `miniprogram/app.json` — 注册新页面

---

## 六、验收标准

- [ ] `MatchPost` 包含 `approval_required` 字段
- [ ] 发布页可选择「报名需要审核」
- [ ] 开启审核后，用户报名状态为 `pending`
- [ ] 帖主收到待审核通知
- [ ] 帖主可在独立页面通过/拒绝报名
- [ ] 审核通过后报名者收到通知
- [ ] 审核通过达到人数上限后帖子变 `full`
- [ ] 未开启审核时报名直接 `approved` 并保持现有满员逻辑
