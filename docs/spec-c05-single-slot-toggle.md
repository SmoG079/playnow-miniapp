# C-05 单个场地时段状态切换规范

## 版本: v1.0
## 日期: 2026-06-12
## 状态: 待实现

---

## 一、当前问题诊断

### 1.1 现状
- `SlotStatus` 枚举已包含 `available`/`locked`/`booked`/`maintenance`
- 手动批量生成接口存在，但无单个 slot 状态修改接口
- 管理员无法快速将某个时段设为维护或恢复可用

### 1.2 缺失
| 缺失项 | 说明 |
|--------|------|
| 单条 slot 更新 API | 无 `PUT /venues/{id}/slots/{slot_id}` |
| 管理员快捷操作 | venue-detail / slot-manage 无状态切换入口 |

---

## 二、需求规格

### 2.1 API
新增：

#### `PATCH /venues/{venue_id}/slots/{slot_id}/status`
- 请求：`{ "status": "available" | "maintenance" }`
- 权限：该 venue 所属 club 的 club_admin / 平台管理员
- 约束：
  - `locked` 和 `booked` 状态不允许直接通过此接口修改（避免与订单流程冲突）
  - 只能将 slot 在 `available` 和 `maintenance` 之间切换
  - 若当前为 `locked`/`booked`，返回 409 Conflict

#### `PUT /venues/{venue_id}/slots/{slot_id}`（可选扩展）
- 请求：`{ "price_override": 120.00, "status": "maintenance" }`
- 本次优先实现 `PATCH /status`，价格覆盖可后续扩展

### 2.2 前端
- `venue-detail` 网格中长按某个 cell 弹出操作菜单：
  - 若 `available` → 「设为维护」
  - 若 `maintenance` → 「恢复可订」
- 仅当当前用户是该 club 管理员时显示操作菜单
- 操作成功后刷新当前日期 slot 列表

- `slot-manage` 页面生成的 slot 列表中，每个 slot 增加状态切换按钮

### 2.3 状态说明
- `available`: 可预订
- `maintenance`: 维护/不可用
- `locked`: 已被锁定待支付（不能手动切换）
- `booked`: 已被预订（不能手动切换）

---

## 三、API 变更

### 3.1 新增路由
```python
@router.patch("/{venue_id}/slots/{slot_id}/status")
async def update_slot_status(
    venue_id: int,
    slot_id: int,
    req: SlotStatusUpdateRequest,
    current_user: User = Depends(_require_club_admin_for_venue),
    db: AsyncSession = Depends(get_db),
):
    ...
```

### 3.2 Schema
```python
class SlotStatusUpdateRequest(BaseModel):
    status: str = Field(..., pattern='^(available|maintenance)$')
```

---

## 四、数据库变更

无新增表/字段，使用现有 `venue_time_slots.status`。

---

## 五、需要修改的文件

### 后端
- `backend/app/api/v1/venues.py` — 新增 `PATCH /{venue_id}/slots/{slot_id}/status`
- `backend/app/schemas/schemas.py` — 新增 `SlotStatusUpdateRequest`

### 前端
- `miniprogram/pages/booking/venue-detail.js` / `.wxml` — 长按弹出状态切换（管理员）
- `miniprogram/pages/publish/slot-manage.js` / `.wxml` — slot 列表增加状态切换按钮

---

## 六、验收标准

- [ ] 新增 `PATCH /venues/{id}/slots/{slot_id}/status` 接口
- [ ] 仅 club 管理员/平台管理员可调用
- [ ] 支持 `available` ↔ `maintenance` 切换
- [ ] `locked`/`booked` 状态返回 409 禁止切换
- [ ] 前端 venue-detail 长按 slot 可切换状态（管理员）
- [ ] 前端 slot-manage 列表可切换状态
- [ ] 切换成功后刷新 slot 列表
