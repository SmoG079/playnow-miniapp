# S-08 约球帖评论系统规范

## 版本: v1.0
## 日期: 2026-06-12
## 状态: 待实现

---

## 一、当前问题诊断

### 1.1 现状
- 无评论表
- 无评论 API
- `post-detail` 页面无评论区域

---

## 二、需求规格

### 2.1 数据模型
新增 `Comment` 表：
```python
class Comment(Base):
    __tablename__ = "comments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    post_id = Column(BigInteger, ForeignKey("match_posts.id"), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    parent_id = Column(BigInteger, ForeignKey("comments.id"), nullable=True)
    content = Column(String(512), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    post = relationship("MatchPost", back_populates="comments")
    user = relationship("User", back_populates="comments")
    replies = relationship("Comment", back_populates="parent")
    parent = relationship("Comment", back_populates="replies", remote_side=[id])
```

`User` 增加关系：
```python
comments = relationship("Comment", back_populates="user")
```

`MatchPost` 增加关系：
```python
comments = relationship("Comment", back_populates="post", order_by="Comment.created_at.desc()")
```

### 2.2 功能范围
- 仅支持一级回复（parent_id 只能为空或指向直接评论）
- 评论内容最大 512 字符
- 支持Emoji
- 帖主/平台管理员可删除评论
- 删除采用软删除：增加 `is_deleted` 字段，保留记录但内容显示「该评论已删除」

### 2.3 API

#### `GET /posts/{id}/comments`
- 返回直接评论列表，按时间倒序
- 每条直接评论包含最近 3 条回复
- 分页：`page`, `page_size`

#### `POST /posts/{id}/comments`
- 请求：`{ "content": "...", "parent_id": null | int }`
- 权限：登录用户
- parent_id 指向的评论必须属于同一 post
- 通知帖主和被回复用户

#### `DELETE /posts/{id}/comments/{comment_id}`
- 权限：评论作者、帖主、平台管理员
- 软删除：设置 `is_deleted=True`

### 2.4 前端
- `post-detail` 页面底部增加评论区域：
  - 评论列表
  - 输入框 + 发送按钮
  - 回复某条评论时显示「回复 @nickname」提示
- 长按/更多操作支持删除（有权限时）

---

## 三、Schema

```python
class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=512)
    parent_id: Optional[int] = None

class CommentBrief(BaseModel):
    id: int
    post_id: int
    user_id: int
    user_nickname: Optional[str]
    user_avatar: Optional[str]
    content: str
    parent_id: Optional[int]
    is_deleted: bool
    created_at: datetime
    reply_count: int = 0
    replies: list["CommentBrief"] = []

    class Config:
        from_attributes = True
```

---

## 四、数据库变更

```sql
CREATE TABLE comments (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    post_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    parent_id BIGINT NULL,
    content VARCHAR(512) NOT NULL,
    is_deleted TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_post_id (post_id),
    INDEX idx_parent_id (parent_id),
    CONSTRAINT fk_comment_post FOREIGN KEY (post_id) REFERENCES match_posts(id),
    CONSTRAINT fk_comment_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_comment_parent FOREIGN KEY (parent_id) REFERENCES comments(id)
);
```

---

## 五、需要修改的文件

### 后端
- `backend/app/models/models.py` — 新增 `Comment` 模型及关系
- `backend/app/schemas/schemas.py` — 新增 `CommentCreate`、`CommentBrief`
- `backend/app/api/v1/posts.py` — 新增评论 CRUD 路由

### 前端
- `miniprogram/pages/common/post-detail.js` / `.wxml` — 评论列表、输入、回复、删除
- `miniprogram/pages/common/post-detail.wxss` — 评论样式

---

## 六、验收标准

- [ ] 数据库存在 `comments` 表
- [ ] 支持对帖子发表评论
- [ ] 支持回复评论（一级）
- [ ] 帖主/平台管理员可删除评论
- [ ] 删除后前端显示「该评论已删除」
- [ ] 评论列表按时间倒序
- [ ] 发表评论后通知帖主/被回复者
- [ ] 评论内容 512 字符限制
