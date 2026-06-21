# 约球帖发布功能完善需求

## 需求概述

约球帖（Match Post）是俱乐部发布的招募帖，用于寻找球友。当前实现缺少权限控制和入口隐藏逻辑。

## 核心规则

1. **只有俱乐部管理员才能发布约球帖**
   - 用户必须至少管理一个俱乐部（`managedClubIds.length > 0`）
   - 后端 API 需要校验用户是否有权限为指定俱乐部发帖

2. **如果用户名下没有俱乐部，隐藏发布入口**
   - 首页「发布」Tab 中的「约球帖」入口需要隐藏
   - 个人中心页面的相关入口也需要根据权限动态显示

## 需要修改的文件

### 后端 (Backend)

#### 1. `backend/app/api/v1/posts.py`

**修改 `create_post` 函数：**

当前实现没有校验用户是否为俱乐部管理员。需要增加：
- 检查 `current_user` 的 `managedClubIds` 是否包含 `req.club_id`
- 如果不包含，返回 403 错误

```python
@router.post("", response_model=PostBrief)
async def create_post(
    req: PostCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 权限校验：只有俱乐部管理员才能发布
    if req.club_id not in (current_user.managed_club_ids or []):
        raise HTTPException(status_code=403, detail="只有俱乐部管理员才能发布约球帖")
    
    # ... 原有逻辑
```

**注意：** 需要确认 `User` 模型是否有 `managed_club_ids` 字段，或者需要通过其他方式获取用户管理的俱乐部列表。

#### 2. `backend/app/api/v1/users.py` (或相关接口)

确保用户信息接口返回 `managedClubIds`，前端需要用它来判断权限。

### 前端 (MiniProgram)

#### 1. `miniprogram/pages/publish/post-create.js`

**修改 `loadClubs` 函数：**

当前实现加载所有俱乐部，应该只加载用户管理的俱乐部：

```javascript
async loadClubs() {
  try {
    // 只加载用户管理的俱乐部
    const managedIds = app.globalData.managedClubIds || [];
    if (managedIds.length === 0) {
      wx.showToast({ title: '您没有管理的俱乐部，无法发布约球帖', icon: 'none' });
      setTimeout(() => wx.navigateBack(), 1500);
      return;
    }
    
    const res = await app.request({ url: '/clubs?page=1&page_size=50' });
    const clubs = (res.items || []).filter(c => managedIds.includes(c.id));
    
    if (clubs.length === 0) {
      wx.showToast({ title: '您没有管理的俱乐部，无法发布约球帖', icon: 'none' });
      setTimeout(() => wx.navigateBack(), 1500);
      return;
    }
    
    this.setData({
      clubIds: clubs.map(c => c.id),
      clubNames: clubs.map(c => c.name),
    });
  } catch (e) { 
    console.error(e); 
  }
}
```

#### 2. `miniprogram/pages/home/index.js` (或发布入口页面)

**隐藏发布入口：**

找到发布按钮/入口的渲染逻辑，根据 `managedClubIds` 判断是否显示「约球帖」选项。

#### 3. `miniprogram/pages/profile/index.js`

**已部分实现：** 当前代码已经有 `hasClub` 判断，但「我的约球帖」入口应该在所有情况下都显示（因为普通用户也可以查看自己报名的帖子）。

需要确认的是：
- 普通用户能看到「我的约球帖」（查看自己报名/发布的）
- 但「发布约球帖」的按钮只有在有俱乐部时才显示

#### 4. `miniprogram/custom-tab-bar/index.js` (或相关导航)

如果「发布」Tab 中有「约球帖」选项，需要根据权限动态显示。

## 测试用例

1. **无俱乐部的用户**
   - 进入发布页面，看不到「约球帖」入口
   - 或者直接访问 `post-create` 页面，提示无权限并返回

2. **有俱乐部的管理员**
   - 正常看到发布入口
   - 发布时只能选择自己管理的俱乐部
   - 发布成功

3. **尝试为不属于自己的俱乐部发帖**
   - 后端返回 403 错误

## 注意事项

1. 后端权限校验是必须的，前端隐藏只是体验优化
2. `managedClubIds` 需要在登录时从用户信息接口获取并存储到 `app.globalData`
3. 如果用户信息接口没有返回 `managedClubIds`，需要修改登录/用户信息接口
