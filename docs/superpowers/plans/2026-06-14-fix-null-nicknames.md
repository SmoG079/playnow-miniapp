# Fix Null Registration Nicknames Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Ensure registered users in match posts display real nicknames instead of "null" by syncing nickname/avatar/phone from the mini-program login flow to the backend `User` model.

**Architecture:** The backend `/auth/login` will store WeChat `session_key`. After login, the frontend sends nickname/avatar via `PUT /users/me` and phone code via `POST /auth/phone`; the backend decrypts the phone server-side using the WeChat `phonenumber.getPhoneNumber` component API.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, WeChat Mini Program JS.

---

## File Structure

- `backend/app/models/models.py` — add `session_key` to `User`.
- `backend/app/core/config.py` — add WeChat component API/access token cache settings if needed.
- `backend/app/api/v1/auth.py` — store `session_key` on login; implement `/auth/phone`.
- `backend/app/api/v1/users.py` — allow `phone` in `PUT /users/me`.
- `backend/app/schemas/schemas.py` — update `UserUpdate` to include `phone`.
- `miniprogram/pages/common/login.js` — collect nickname/avatar/phone and sync to backend.
- `miniprogram/pages/common/login.wxml` — bind nickname input and avatar.
- `miniprogram/app.js` — no changes unless helper needed.

---

## Task 1: Add session_key to User model

**Files:**
- Modify: `backend/app/models/models.py`

- [ ] **Step 1: Add `session_key` column**

In `User` model, after `phone`:

```python
    session_key = Column(String(64))
```

---

## Task 2: Update login to store session_key

**Files:**
- Modify: `backend/app/api/v1/auth.py`

- [ ] **Step 1: Store session_key from jscode2session response**

In `wx_login`, after extracting `openid`:

```python
    session_key = data.get("session_key")
    if not session_key:
        raise HTTPException(status_code=400, detail="WeChat did not return session_key")

    result = await db.execute(select(User).where(User.openid == openid))
    user = result.scalar_one_or_none()
    if not user:
        user = User(openid=openid, unionid=data.get("unionid"), session_key=session_key)
        db.add(user)
        await db.flush()
    else:
        user.session_key = session_key
```

---

## Task 3: Implement /auth/phone with server-side decryption

**Files:**
- Modify: `backend/app/api/v1/auth.py`
- Modify: `backend/app/core/config.py` (if access token helper needed)

WeChat modern `getPhoneNumber` returns a `code`. Server-side decryption uses the component API:

```
POST https://api.weixin.qq.com/wxa/business/getuserphonenumber?access_token=ACCESS_TOKEN
Body: {"code": "..."}
```

The `access_token` is obtained via:
```
GET https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid=APPID&secret=APPSECRET
```

- [ ] **Step 1: Add access token helper**

Add near top of `auth.py`:

```python
import time
import logging

logger = logging.getLogger(__name__)
_access_token_cache = {"token": None, "expires_at": 0}


async def _get_wx_access_token() -> str:
    now = int(time.time())
    if _access_token_cache["token"] and _access_token_cache["expires_at"] > now + 60:
        return _access_token_cache["token"]

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.weixin.qq.com/cgi-bin/token",
            params={
                "grant_type": "client_credential",
                "appid": settings.WX_APP_ID,
                "secret": settings.WX_APP_SECRET,
            },
        )
        data = resp.json()

    token = data.get("access_token")
    if not token:
        raise HTTPException(status_code=502, detail=f"WeChat access_token error: {data}")

    _access_token_cache["token"] = token
    _access_token_cache["expires_at"] = now + data.get("expires_in", 7200)
    return token
```

- [ ] **Step 2: Implement /auth/phone**

Replace the existing `/auth/phone` endpoint:

```python
@router.post("/phone")
async def get_phone(
    req: PhoneRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Decrypt WeChat phone number using the component API and save it."""
    if not req.code:
        raise HTTPException(status_code=400, detail="Missing phone code")

    access_token = await _get_wx_access_token()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.weixin.qq.com/wxa/business/getuserphonenumber?access_token={access_token}",
            json={"code": req.code},
        )
        data = resp.json()

    if data.get("errcode") != 0:
        raise HTTPException(status_code=502, detail=f"WeChat phone decrypt failed: {data}")

    phone_info = data.get("phone_info", {})
    phone = phone_info.get("purePhoneNumber")
    if not phone:
        raise HTTPException(status_code=502, detail="WeChat did not return phone number")

    current_user.phone = phone
    await db.commit()
    return {"phone": phone}
```

---

## Task 4: Allow phone in UserUpdate

**Files:**
- Modify: `backend/app/schemas/schemas.py`
- Modify: `backend/app/api/v1/users.py`

- [ ] **Step 1: Update schema**

```python
class UserUpdate(BaseModel):
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    ntrp_level: Optional[Decimal] = Field(None, ge=1.0, le=7.0)
```

- [ ] **Step 2: Update PUT /users/me**

```python
    if req.phone is not None:
        current_user.phone = req.phone
```

---

## Task 5: Frontend login page collect and sync profile

**Files:**
- Modify: `miniprogram/pages/common/login.js`
- Modify: `miniprogram/pages/common/login.wxml`

- [ ] **Step 1: Update data and handlers**

```javascript
Page({
  data: {
    loading: false,
    agreed: false,
    redirect: '',
    nickname: '',
    avatarUrl: '',
  },

  onLoad(options) {
    if (app.globalData.token) {
      wx.switchTab({ url: '/pages/home/index' });
    }
    if (options && options.redirect) {
      this.setData({ redirect: decodeURIComponent(options.redirect) });
    }
  },

  onNicknameInput(e) {
    this.setData({ nickname: e.detail.value });
  },

  onChooseAvatar(e) {
    this.setData({ avatarUrl: e.detail.avatarUrl });
  },

  async onGetPhoneNumber(e) {
    if (!app.globalData.token) {
      wx.showToast({ title: '请先登录', icon: 'none' });
      return;
    }
    if (!e.detail.code) {
      wx.showToast({ title: '授权失败', icon: 'none' });
      return;
    }
    try {
      await app.request({
        url: '/auth/phone',
        method: 'POST',
        data: { code: e.detail.code },
      });
      wx.showToast({ title: '手机号已保存', icon: 'success' });
    } catch (err) {
      wx.showToast({ title: '手机号保存失败', icon: 'none' });
    }
  },

  async onLogin() {
    if (!this.data.agreed) {
      wx.showToast({ title: '请先同意用户协议', icon: 'none' });
      return;
    }

    this.setData({ loading: true });
    try {
      await auth.login();

      // Sync profile after login (JWT now available)
      const { nickname, avatarUrl } = this.data;
      if (nickname || avatarUrl) {
        try {
          await app.request({
            url: '/users/me',
            method: 'PUT',
            data: { nickname, avatar_url: avatarUrl },
          });
          await app.fetchUserInfo();
        } catch (e) {
          console.error('Sync profile failed', e);
        }
      }

      const redirect = this.data.redirect;
      if (redirect) {
        if (redirect.startsWith('/pages/') && redirect.includes('?')) {
          wx.reLaunch({ url: redirect });
        } else {
          wx.reLaunch({ url: redirect });
        }
      } else {
        wx.switchTab({ url: '/pages/home/index' });
      }
    } catch (e) {
      wx.showToast({ title: '登录失败，请重试', icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
  },
```

- [ ] **Step 2: Update login.wxml**

Bind nickname input:

```xml
    <view class="nickname-input">
      <input
        class="input"
        type="nickname"
        placeholder="请输入昵称"
        value="{{nickname}}"
        bindinput="onNicknameInput"
      />
    </view>
```

Avatar image already bound to `avatarUrl`.

---

## Task 6: Update fix-progress documentation

**Files:**
- Modify: `docs/module-b-fix-progress.md`

- [ ] **Step 1: Add changelog entry**

Add under changelog:
- 修复报名用户昵称为 null：登录时保存 session_key，前端同步 nickname/avatar，后端实现 `/auth/phone` 解密手机号

---

## Verification

- Run `python -m py_compile` on all modified backend files.
- Run `python -c "from app.main import app"` to verify imports.
- Test mini-program login: set nickname, avatar, phone; verify `/users/me` returns populated fields.
- Create a match post registration and verify `post-detail`/`post-registration-approve` shows nickname.
