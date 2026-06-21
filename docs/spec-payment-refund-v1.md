# 微信支付完善与退款回调实现规范

## 版本: v1.0
## 日期: 2025-06-12
## 状态: 待实现

---

## 一、当前问题诊断

### 1.1 支付回调 (wx-notify)
**状态**: 已实现基础功能，但存在以下问题

| 问题 | 严重程度 | 说明 |
|------|---------|------|
| 无退款回调处理 | 🔴 高 | 只处理了支付成功，未处理退款成功回调 |
| 无重复通知幂等 | 🟡 中 | 仅检查了 `status == paid`，但退款状态未做幂等 |
| 无异常订单处理 | 🟡 中 | 未处理支付失败、关闭订单等情况 |
| 无日志记录 | 🟢 低 | 回调内容未记录，排查问题困难 |

### 1.2 退款流程
**状态**: 同步退款已实现，但缺少异步回调处理

| 问题 | 严重程度 | 说明 |
|------|---------|------|
| 退款回调未处理 | 🔴 高 | 微信退款是异步的，需要回调更新状态 |
| 退款金额计算错误 | 🔴 高 | `cancel` 接口计算了阶梯退款，但 `refund` 接口全额退款 |
| 无退款失败处理 | 🟡 中 | 退款API调用失败无重试机制 |
| 无退款记录表 | 🟡 中 | 无法追踪退款历史 |

### 1.3 数据模型缺失

| 缺失字段/表 | 说明 |
|------------|------|
| `BookingOrder.refund_id` | 微信退款单号 |
| `BookingOrder.refund_time` | 退款完成时间 |
| `RefundRecord` 表 | 退款记录独立表 |
| `PaymentLog` 表 | 支付/退款日志 |

---

## 二、需求规格

### 2.1 支付回调增强 (wx-notify)

**输入**: 微信回调请求 (Headers + Body)
**处理逻辑**:
1. 验证签名和解密
2. 根据 `event_type` 分发处理:
   - `TRANSACTION.SUCCESS` - 支付成功
   - `TRANSACTION.CLOSED` - 订单关闭
   - `REFUND.SUCCESS` - 退款成功
   - `REFUND.ABNORMAL` - 退款异常
   - `REFUND.CLOSED` - 退款关闭
3. 幂等检查: 根据 `out_trade_no` + `transaction_id` + `event_type` 去重
4. 记录回调日志

**输出**: `{"code": "SUCCESS"}` 或 `{"code": "FAIL", "message": "..."}`

### 2.2 退款回调处理 (wx-refund-notify)

**新接口**: `POST /api/v1/bookings/wx-refund-notify`

**输入**: 微信退款回调
**处理逻辑**:
1. 验证签名和解密
2. 解析 `out_refund_no`, `out_trade_no`, `refund_status`
3. 更新订单状态:
   - `SUCCESS` → `refunded`
   - `ABNORMAL` → 记录异常，人工介入
   - `CLOSED` → 退款关闭，恢复订单状态
4. 发送用户通知

### 2.3 退款流程统一

**当前问题**: `cancel` 和 `refund` 两个接口逻辑不统一

**解决方案**: 
- `POST /{booking_id}/cancel` - 用户取消（自动计算退款金额，调用微信退款）
- `POST /{booking_id}/refund` - 管理员强制退款（全额或指定金额）

**退款金额规则**:
- 开场前 ≥24小时: 全额退款
- 开场前 0-24小时: 50%退款
- 开场后: 不可退款

### 2.4 数据模型变更

**BookingOrder 表新增字段**:
```python
refund_id = Column(String(64))          # 微信退款单号
refund_time = Column(DateTime)          # 退款完成时间
refund_status = Column(String(32))      # 退款状态: pending/success/failed/closed
```

**新增 RefundRecord 表**:
```python
class RefundRecord(Base):
    id = Column(BigInteger, primary_key=True)
    order_id = Column(BigInteger, ForeignKey("booking_orders.id"))
    out_refund_no = Column(String(32), unique=True)  # 商户退款单号
    wx_refund_id = Column(String(64))                # 微信退款单号
    amount = Column(DECIMAL(10, 2))                  # 退款金额
    reason = Column(String(256))                     # 退款原因
    status = Column(String(32))                     # 状态
    created_at = Column(DateTime)
    completed_at = Column(DateTime)
```

**新增 PaymentLog 表**:
```python
class PaymentLog(Base):
    id = Column(BigInteger, primary_key=True)
    order_id = Column(BigInteger)
    type = Column(String(32))           # pay/refund
    event_type = Column(String(64))     # TRANSACTION.SUCCESS/REFUND.SUCCESS
    raw_data = Column(JSON)             # 原始回调数据
    created_at = Column(DateTime)
```

---

## 三、API 变更

### 3.1 现有接口修改

| 接口 | 变更 |
|------|------|
| `POST /wx-notify` | 增加退款回调处理分支 |
| `POST /{id}/cancel` | 自动调用微信退款API，不再只是标记状态 |
| `POST /{id}/refund` | 支持部分退款，记录退款单号 |

### 3.2 新增接口

| 接口 | 说明 |
|------|------|
| `POST /wx-refund-notify` | 微信退款回调 |
| `GET /{id}/refund-records` | 查询退款记录 |

---

## 四、时序图

### 4.1 支付成功流程
```
用户 → 小程序 → 微信支付 → 微信服务器
                        ↓
后端 ← 回调 ← 微信服务器
  ↓
更新订单状态: pending → paid
创建结算记录
发送通知
```

### 4.2 退款流程
```
用户 → 取消订单 → 后端计算退款金额
                    ↓
                调用微信退款API
                    ↓
                更新订单: paid → refunding
                创建退款记录
                    ↓
微信服务器 → 回调 → 后端
                    ↓
                更新订单: refunding → refunded
                更新退款记录
                释放场地
                发送通知
```

---

## 五、测试用例

### 5.1 支付回调测试
- [ ] 正常支付成功回调
- [ ] 重复回调幂等
- [ ] 签名验证失败
- [ ] 订单不存在

### 5.2 退款测试
- [ ] 开场前24小时取消，全额退款
- [ ] 开场前2小时取消，50%退款
- [ ] 开场后取消，拒绝退款
- [ ] 退款回调成功
- [ ] 退款回调异常

---

## 六、数据库迁移

```sql
-- BookingOrder 新增字段
ALTER TABLE booking_orders ADD COLUMN refund_id VARCHAR(64) AFTER wx_transaction_id;
ALTER TABLE booking_orders ADD COLUMN refund_time DATETIME AFTER refund_id;
ALTER TABLE booking_orders ADD COLUMN refund_status VARCHAR(32) DEFAULT 'pending';

-- 退款记录表
CREATE TABLE refund_records (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    order_id BIGINT NOT NULL,
    out_refund_no VARCHAR(32) NOT NULL UNIQUE,
    wx_refund_id VARCHAR(64),
    amount DECIMAL(10,2) NOT NULL,
    reason VARCHAR(256),
    status VARCHAR(32) DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    INDEX idx_order_id (order_id)
);

-- 支付日志表
CREATE TABLE payment_logs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    order_id BIGINT,
    type VARCHAR(32),
    event_type VARCHAR(64),
    raw_data JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_order_id (order_id)
);
```

---

## 七、实现优先级

| 优先级 | 任务 | 预估工时 |
|--------|------|---------|
| P0 | 退款回调接口 (`wx-refund-notify`) | 2h |
| P0 | 支付回调增加退款分支 | 1h |
| P0 | 统一 cancel/refund 逻辑 | 2h |
| P1 | 数据模型变更 + 迁移 | 1.5h |
| P1 | 退款记录查询API | 1h |
| P2 | 支付日志记录 | 1h |
| P2 | 退款失败重试机制 | 2h |

**总计**: ~10.5小时

---

## 八、验收标准

- [ ] 支付成功回调正常处理，订单状态更新为 paid
- [ ] 退款成功回调正常处理，订单状态更新为 refunded
- [ ] 用户取消订单自动触发微信退款
- [ ] 退款金额按规则计算（24h全额/0-24h半额/0h拒绝）
- [ ] 重复回调不重复处理（幂等）
- [ ] 退款记录可查询
- [ ] 所有回调记录日志

---

**规范制定**: Hermes (Kimi)
**实现者**: Claude Code
**审核者**: Hermes (Kimi)
