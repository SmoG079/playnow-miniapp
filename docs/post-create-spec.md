# 约球帖发布功能规范 (SSD)

## 需求背景
约球帖（Match Post）是俱乐部发布的招募帖。当前实现缺少权限控制：任何人都能发布，且发布入口始终可见。

## 业务规则（不可违背）

### 规则 1：发布权限
- **只有俱乐部管理员才能发布约球帖**
- 俱乐部管理员定义：`managedClubIds.length > 0`
- 后端必须校验：用户管理的俱乐部列表包含 `req.club_id`
- 违规后果：返回 HTTP 403

### 规则 2：入口隐藏
- **如果用户名下没有俱乐部，隐藏「发布约球帖」入口**
- 隐藏范围：
  - 首页/发布页面的「约球帖」选项
  - 个人中心页面的「发布约球帖」快捷入口（如有）
- 直接访问 `post-create` 页面时：提示无权限并返回上一页

### 规则 3：俱乐部选择范围
- 发布页面中的俱乐部选择器，**只显示用户管理的俱乐部**
- 不可选择未管理的俱乐部

## 接口规范

### POST /api/v1/posts

**请求头：**
```
Authorization: Bearer {token}
```

**请求体：**
```json
{
  "club_id": 1,
  "title": "周末羽毛球3缺1",
  "sport_type": "羽毛球",
  "preferred_date": "2026-06-15",
  "preferred_start": "14:00",
  "preferred_end": "16:00",
  "players_needed": 1,
  "level_required": "中级",
  "notes": ""
}
```

**响应（成功）：**
```json
{
  "id": 1,
  "club_id": 1,
  "user_id": 123,
  "title": "周末羽毛球3缺1",
  ...
}
```

**响应（无权限）：**
```json
{
  "detail": "只有俱乐部管理员才能发布约球帖"
}
```
HTTP Status: 403

## 数据模型

### User 模型需暴露字段
```python
managed_club_ids: List[int]  # 用户管理的俱乐部ID列表
```

### 当前已有
- `app.globalData.managedClubIds` 已存在
- `app.globalData.role` 已存在

## 文件修改清单

### 后端
| 文件 | 修改内容 |
|------|----------|
| `backend/app/api/v1/posts.py` | `create_post` 增加权限校验 |
| `backend/app/api/v1/auth.py` 或 `users.py` | 确保登录接口返回 `managed_club_ids` |

### 前端
| 文件 | 修改内容 |
|------|----------|
| `miniprogram/pages/publish/post-create.js` | 加载只显示管理的俱乐部；无俱乐部时提示返回 |
| `miniprogram/pages/publish/post-create.wxml` | 无俱乐部时显示空状态提示 |
| `miniprogram/pages/home/index.js` | 发布入口根据 `managedClubIds` 动态显示 |
| `miniprogram/pages/home/index.wxml` | 条件渲染发布入口 |

## 验收标准（测试用例）

### TC-1：无俱乐部用户访问发布页面
**前置：** 用户未管理任何俱乐部（`managedClubIds = []`）
**操作：** 进入 `post-create` 页面
**预期：**
- 页面显示提示："您没有管理的俱乐部，无法发布约球帖"
- 1.5秒后自动返回上一页

### TC-2：无俱乐部用户看不到发布入口
**前置：** 用户未管理任何俱乐部
**操作：** 浏览首页/发布页面
**预期：** 「约球帖」发布入口不可见

### TC-3：有俱乐部用户正常发布
**前置：** 用户管理俱乐部 ID = [1, 2]
**操作：** 进入发布页面，选择俱乐部 1，填写信息，提交
**预期：** 发布成功，返回帖子详情

### TC-4：后端权限校验
**前置：** 用户管理俱乐部 ID = [1]，请求体 `club_id = 2`
**操作：** 调用 POST /api/v1/posts
**预期：** 返回 403，错误信息 "只有俱乐部管理员才能发布约球帖"

### TC-5：俱乐部选择器范围
**前置：** 用户管理俱乐部 ID = [1, 3]
**操作：** 进入发布页面，打开俱乐部选择器
**预期：** 只显示俱乐部 1 和 3，不显示其他俱乐部

## 注意事项
1. 后端权限校验是最终防线，前端隐藏只是体验优化
2. `managedClubIds` 在登录时已写入 `app.globalData`，无需额外请求
3. 保持现有代码风格，不引入新依赖
