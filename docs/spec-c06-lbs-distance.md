# C-06 俱乐部列表 LBS 距离计算规范

## 版本: v1.0
## 日期: 2026-06-12
## 状态: 待实现

---

## 一、当前问题诊断

### 1.1 后端
| 问题 | 说明 |
|------|------|
| `GET /clubs` 已接受 `lat`/`lng` 参数 | `backend/app/api/v1/clubs.py:20-23` |
| 未实际计算距离 | 查询仅按 `Club.id.desc()` 排序，未使用经纬度 |
| 响应模型无 `distance` 字段 | `ClubBrief` 缺少距离字段 |

### 1.2 前端
| 问题 | 说明 |
|------|------|
| `club-list.js` 已获取用户位置 | 第 28-38 行调用 `wx.getLocation` |
| 已携带 `lat`/`lng` 请求 | 第 44-46 行 |
| 未展示距离 | `club-list.wxml` 无距离标签 |
| 无排序切换 | 俱乐部列表无「距离最近」排序选项 |

---

## 二、需求规格

### 2.1 后端距离计算
- 使用 Haversine 公式计算用户位置与俱乐部经纬度之间距离
- 单位：km，保留 1 位小数
- 当俱乐部无经纬度时，`distance` 返回 `null`
- 支持 `sort_by=distance` 参数按距离升序排列

### 2.2 前端展示
- 俱乐部卡片显示距离标签（如 `2.5km`）
- 列表顶部增加排序切换：「默认」/「距离最近」
- 未授权位置时提示开启位置权限；用户拒绝则回退到默认排序

---

## 三、API 变更

### 3.1 `GET /api/v1/clubs`
**请求参数:**
```
lat={float}&lng={float}&sort_by=distance&sport={str}&keyword={str}&page=1&page_size=20
```

**响应字段新增:**
```json
{
  "items": [
    {
      "id": 1,
      "name": "...
      "distance": 2.5
    }
  ]
}
```

### 3.2 新增工具函数
- `backend/app/utils/geo.py` — `haversine(lat1, lng1, lat2, lng2) -> float | None`

---

## 四、数据模型变更

`ClubBrief` schema 增加字段：
```python
distance: Optional[float] = None  # km, 保留1位小数
```

---

## 五、需要修改的文件

### 后端
- `backend/app/api/v1/clubs.py` — 在 `list_clubs` 中计算并排序距离
- `backend/app/schemas/schemas.py` — `ClubBrief` 增加 `distance`
- `backend/app/utils/geo.py` — 新增 Haversine 工具（如不存在则创建）

### 前端
- `miniprogram/pages/booking/club-list.js` — 增加 `sortBy` 状态，按排序调用接口
- `miniprogram/pages/booking/club-list.wxml` — 增加排序栏和距离标签
- `miniprogram/pages/booking/club-list.wxss` — 样式（如需要）

---

## 六、验收标准

- [ ] 后端 `GET /clubs?lat=&lng=&sort_by=distance` 返回按距离升序的俱乐部列表
- [ ] 每个俱乐部条目包含 `distance` 字段（有坐标时）
- [ ] 无坐标俱乐部排在最后，`distance` 为 `null`
- [ ] 前端俱乐部卡片显示距离
- [ ] 前端支持切换「默认」/「距离最近」排序
- [ ] 未授权位置时按默认排序且不报错
