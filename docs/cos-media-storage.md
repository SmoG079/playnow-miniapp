> 2026-10-09 更新：已按用户授权创建独立私有桶 `tennis-miniapp-private-1300427458`，新认证材料通过鉴权 API 下载。旧公开桶 `doc/*` 已拒绝匿名 GetObject（含历史版本）；其他图片目录公读保持。当前认证目录对象/历史版本与正式数据库认证链接均为零。下文为历史配置记录；实际发布验收见 `docs/code-review-20261009.md`。

# PlayNow 媒体资源存储（腾讯云 COS）

头像、球场照片、比赛图片、宣传视频等静态资源统一存放腾讯云 COS，不再依赖服务器本地磁盘 `backend/uploads`。后端上传链路已于 2026-10-07 切换到 COS 并完成真实上传验证；CDN 因域名备案受阻而暂缓，当前直接用 COS 默认域名提供访问。

本文档覆盖**使用方式**与**注意事项**。文末记录验证证据与尚未落地的边界。

## 当前配置

| 项 | 值 |
|---|---|
| 桶名 | `tennis-miniapp-img-1300427458` |
| 地域 | `ap-shanghai`（与服务器 101.34.213.125 同地域） |
| 权限 | 公有读私有写（AllUsers READ；写操作必须签名） |
| 版本控制 | Enabled，覆盖/删除后可恢复历史版本 |
| 访问域名 | `https://tennis-miniapp-img-1300427458.cos.ap-shanghai.myqcloud.com` |
| 归属账号 | UIN 100011726123（AppId 1300427458） |
| CDN 加速 | 未接入。`AddCdnDomain` 返回 `ResourceUnavailable.CdnHostNoIcp`，域名未在腾讯云侧查到 ICP 备案 |

对象前缀约定（后续做生命周期、批量操作、CDN 缓存规则时按前缀处理）：

| 前缀 | 用途 |
|---|---|
| `avatar/` | 用户头像 |
| `court/` | 球场、场馆照片 |
| `post/` | 约球帖与比赛图片 |
| `video/` | 宣传视频 |
| `doc/` | 俱乐部认证材料等敏感文件（**当前公开可读，见注意事项 10**） |
| `upload/` | 其它图片，兼容历史本地文件名 |

前缀白名单定义在 `backend/app/services/storage.py` 的 `PREFIXES`，接口收到白名单外的 `file_type` 一律回落到 `upload/`。

## 使用方式

### 后端上传（唯一推荐入口）

`POST /api/v1/upload`（`backend/app/main.py`）已切换为写入 COS，接口契约 `{url, filename}` 保持不变（`filename` 现为含前缀的对象 key）。前端无需任何调整。

实现位于 `backend/app/services/storage.py`（**以源码为准**，下列代码为同步说明）：

```python
import os, uuid
from typing import Optional
from qcloud_cos import CosConfig, CosS3Client
from app.core.config import get_settings
from app.core.logger import get_logger

settings = get_settings()
logger = get_logger(__name__)
_client: Optional[CosS3Client] = None

# 扩展名 -> MIME，避免直接信任客户端上传的 content_type
MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".gif": "image/gif", ".mp4": "video/mp4",
}

PREFIXES = {"avatar", "court", "post", "video", "doc", "upload"}

# 回退目录，同时是 /uploads 静态挂载的根目录（main.py 复用此常量）
LOCAL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads"))


def is_configured() -> bool:
    """COS 密钥是否齐备；缺任一项即走本地磁盘回退。"""
    return bool(settings.OSS_ACCESS_KEY_ID and settings.OSS_ACCESS_KEY_SECRET
                and settings.OSS_BUCKET_NAME)


def active_backend() -> str:
    return "cos" if is_configured() else "local"


def _get_client() -> CosS3Client:
    """惰性创建全局复用的 COS 客户端（仅在 is_configured() 为真时调用）。"""
    global _client
    if _client is None:
        _client = CosS3Client(CosConfig(
            Region=settings.COS_REGION,
            SecretId=settings.OSS_ACCESS_KEY_ID,
            SecretKey=settings.OSS_ACCESS_KEY_SECRET,
            Token=settings.OSS_SESSION_TOKEN or None,
            Scheme="https",
        ))
    return _client


def build_key(prefix: str, ext: str) -> str:
    """生成对象 key，形如 court/9f2a....jpg；前缀不在白名单内回落 upload/。"""
    safe = prefix if prefix in PREFIXES else "upload"
    return f"{safe}/{uuid.uuid4().hex}{ext.lower()}"


def public_url(key: str) -> str:
    """桶为公有读，直接拼默认域名即可访问。"""
    return f"https://{settings.OSS_BUCKET_NAME}.cos.{settings.COS_REGION}.myqcloud.com/{key}"


def put_object(key: str, content: bytes, ext: str = "") -> str:
    if not is_configured():
        # 回退本地磁盘：CI 与本地开发无需云凭证即可跑通上传链路
        logger.warning("COS 未配置，上传落本地磁盘（非生产预期）：key=%s", key)
        path = _local_path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)
        return f"{settings.PUBLIC_BASE_URL}/uploads/{key}"

    _get_client().put_object(
        Bucket=settings.OSS_BUCKET_NAME, Key=key, Body=content,
        ContentType=MIME.get(ext.lower(), "application/octet-stream"),
    )
    return public_url(key)


def delete_object(key: str) -> None:
    if not is_configured():
        try:
            os.remove(_local_path(key))
        except FileNotFoundError:
            pass
        return
    _get_client().delete_object(Bucket=settings.OSS_BUCKET_NAME, Key=key)
```

`_local_path()` 会对 key 做 `abspath` 并校验仍在 `LOCAL_DIR` 内，阻断 `../` 越界写入。

**为什么保留本地回退**：项目 CI 惯例是不注入云凭证（`.github/workflows/deploy.yml` 的 backend job 只起本地 MySQL/Redis）。若密钥缺失直接抛错，`tests/http_fullflow.py` 的 `POST /upload` 会拿到 502 而失败。回退后 CI 走本地磁盘、生产走 COS，同一套断言都成立。

> ⚠️ 回退是**静默降级风险点**：生产 `.env` 密钥若被误删或失效，上传会落到本地磁盘且返回的 URL 仍可访问，不易察觉。因此回退时**每次上传都打 WARNING**，并在应用启动时打印 `media storage backend: cos|local` 便于排障。生产应为 `cos`。


`backend/app/main.py` 当前的端点实现（`file_type` 由前端 `formData` 传入，`from fastapi import Form`、`from fastapi.concurrency import run_in_threadpool`）：

```python
@app.post("/api/v1/upload")
async def upload_file(
    file: UploadFile = File(...),
    file_type: str = Form("upload"),
    _=Depends(get_current_user),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in settings.UPLOAD_ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="仅支持 jpg/png/webp/gif 图片")
    content = await file.read()
    if len(content) > settings.UPLOAD_MAX_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"图片不能超过 {settings.UPLOAD_MAX_MB}MB")
    key = storage.build_key(file_type, ext)
    try:
        url = await run_in_threadpool(storage.put_object, key, content, ext)
    except Exception:
        logger.error("media upload failed: key=%s", key, exc_info=True)
        raise HTTPException(status_code=502, detail="图片上传失败，请稍后重试")
    logger.info("media upload: %s -> %s (%d bytes)", key, storage.active_backend(), len(content))
    return {"url": url, "filename": key}
```

两点说明：

- COS 调用是同步阻塞的，用 `run_in_threadpool` 包装，避免阻塞事件循环。
- `app.mount("/uploads", StaticFiles(directory=storage.LOCAL_DIR))` **保留**：既兼容数据库中已存在的 `/uploads/<uuid>` 历史链接（线上 2 个文件），也是未配置 COS 时回退文件的对外出口。挂载目录改为引用 `storage.LOCAL_DIR`，避免路径在两处各写一遍。

### 环境配置

`backend/app/core/config.py` 复用既有的 `OSS_*` 字段，并新增 `COS_REGION`、`OSS_SESSION_TOKEN`（后者仅 STS 临时凭证需要，永久密钥留空）。生产环境 `backend/.env` 需要补齐：

```env
# backend/.env （仅服务器，不入库）
OSS_ENDPOINT=cos.ap-shanghai.myqcloud.com
OSS_BUCKET_NAME=tennis-miniapp-img-1300427458
OSS_ACCESS_KEY_ID=<子账号 SecretId>
OSS_ACCESS_KEY_SECRET=<子账号 SecretKey>
COS_REGION=ap-shanghai
```

> **部署前提**：生产服务器 `.env` 已按下文配置完毕，上传走 COS。**若密钥缺失，接口不会报错，而是静默回退本地磁盘**（返回 `PUBLIC_BASE_URL/uploads/<key>`）并在日志打 WARNING。部署后用日志中的 `media storage backend: cos` 确认后端正确，或直接看上传返回的 URL 域名是否为 `myqcloud.com`。

`backend/requirements.txt` 已加入 `cos-python-sdk-v5==1.9.44`。`oss2==2.19.0` 目前没有任何代码引用，确认无其它用途后可移除。

### 密钥与权限（已配置）

| 项 | 值 |
|---|---|
| CAM 子用户 | `playnow-cos`（Uin 100053480422，无控制台登录权限） |
| 自定义策略 | `playnow-cos-media`（PolicyId 288832582） |
| 允许动作 | `cos:PutObject` / `cos:GetObject` / `cos:DeleteObject` |
| 资源范围 | `qcs::cos:ap-shanghai:uid/1300427458:tennis-miniapp-img-1300427458/*` |
| 密钥类型 | 永久密钥（非 STS），`OSS_SESSION_TOKEN` 留空 |
| 存放位置 | 服务器 `/home/ubuntu/playnow-miniapp/backend/.env`（2026-10-07 写入，原文件备份为 `.env.bak.20261007163457`） |

权限边界已实测：上传、匿名读取、删除均通过；列举桶对象（`cos:GetBucket`）与读取桶 ACL 均返回 `AccessDenied`。**不要在生产使用主账号密钥**。CI 部署不会覆盖服务器上的 `.env`，因此密钥只需配置一次。

### 前端

- 上传入口唯一：`frontend/src/services/api.ts` 的 `uploadFile()`（`uni.uploadFile` → `API_BASE_URL + "/upload"`）
- 展示统一走 `<Photo>` 组件（`frontend/src/components/Photo.vue`，easycom `^Photo$`）

切 COS 不需要改动上传与展示的调用方式：`uploadFile()` 仍指向 `API_BASE_URL`，合法域名配置不变；展示侧只认后端返回的 `url`。

`uploadFile()` 已增加 `fileType` 参数（默认 `upload`，向后兼容），透传到 `uni.uploadFile` 的 `formData.file_type`（其余逻辑不变）：

```ts
export function uploadFile(filePath: string, fileType = "upload"): Promise<{ url: string }> {
  return new Promise((resolve, reject) => {
    uni.uploadFile({
      url: API_BASE_URL + "/upload",
      filePath,
      name: "file",
      formData: { file_type: fileType },
      header: { Authorization: `Bearer ${uni.getStorageSync("access_token")}` },
      success: (response) => { /* 原逻辑不变 */ },
      fail: (err) => { /* 原逻辑不变 */ },
    });
  });
}
```

各调用点传入的前缀：

| 调用点 | fileType |
|---|---|
| `pages/profile/edit.vue` 头像 | `avatar` |
| `pages/publish/venue-manage.vue` 场地封面 | `court` |
| `pages/publish/post-create.vue` 约球帖图片 | `post` |
| `pages/publish/tournament-create.vue` 比赛图片 | `post` |
| `pages/publish/club-create.vue` 俱乐部图片 | `post` |
| `pages/publish/club-create.vue` 认证材料 | `doc` |

### 运维与脚本直传

服务器上临时上传单个文件（不经过 API）：

```python
from qcloud_cos import CosConfig, CosS3Client
client = CosS3Client(CosConfig(Region="ap-shanghai", SecretId=..., SecretKey=...))
client.put_object(
    Bucket="tennis-miniapp-img-1300427458",
    Key="court/example.jpg",
    Body=open("example.jpg", "rb"),
)
```

## 注意事项

### 1. 上传必须走后端中转，不要指望小程序直传

`wx.uploadFile` 的目标域名必须在小程序后台配置为合法域名，而该配置要求上传归属校验文件到域名根目录，`myqcloud.com` 无法完成校验，因此**不能用 COS 域名作为上传域名**。上传链路固定为：

```
小程序 --wx.uploadFile--> 自建后端 /api/v1/upload --COS SDK--> COS 桶 --> 返回 COS URL
```

H5 端若需要直传，可用 CAM STS 临时密钥（仅授 `cos:PutObject`），但小程序端仍只能走中转。

### 2. 显示不需要备案，上传域名和 CDN 才需要

`<image>` 与 `<video>` 组件的 `src` 不受服务器域名白名单限制，所以 COS 默认域名**不需要备案就能显示图片和播放视频**，这是当前方案能立即上线的原因。受备案约束的只有两处：`wx.uploadFile`/`wx.request` 的合法域名（即自建 API 域名）、以及 CDN 加速域名。

### 3. 费用结构与优化重点

| 费用项 | 单价 | 说明 |
|---|---|---|
| 标准存储 | ¥0.118/GB/月 | 存量 65 GB 约 ¥7.7/月 |
| 读写请求 | 读 ¥0.01/万次 | 基本可忽略 |
| 外网下行 | **¥0.5/GB** | 真正的成本大头 |

服务器与桶同地域（均为 ap-shanghai），服务器上传走内网不计外网下行流量；只有小程序用户**下载、播放**才产生外网下行费。因此优化重点是**压缩源文件**：球场照片压到 1080p / 质量 80（通常 200–400 KB），宣传视频 720p / 码率 2 Mbps 以内。存储类型保持标准存储即可——低频存储读请求单价高 5 倍且收取回费，对需要随时展示的资源是负优化。

### 4. 公有读意味着链接即权限

任何拿到 URL 的人都能访问，**不要往上放合同、证件、订单截图等敏感文件**。当前不配 Referer 防盗链：小程序发起的请求 Referer 不统一，白名单容易误伤自己。若将来出现盗链，优先用 CDN 签名 URL 收敛。

### 5. 版本控制会让存储量持续增长

桶已开启版本控制，覆盖同名对象不会删除旧版本，误删可恢复。代价是**同名文件反复覆盖会累积存储量**。由于上传文件名是随机 hex，正常业务不会重复覆盖，风险主要来自运维手工操作（如固定文件名覆盖上传）。如需要，可对 `upload/` 前缀配置生命周期规则自动清理非当前版本。

### 6. 视频上传需要同时放开三处限制

当前 `UPLOAD_MAX_MB=5` 与两处 Nginx 的 `client_max_body_size 20M` 只够图片。上传大视频必须同时调整：后端 `UPLOAD_MAX_MB`、容器内 `backend/nginx/nginx.conf`、**宿主机 Nginx**（8443 端口那一层，不在仓库里）。超过 50 MB 建议改用 COS 分块上传（`upload_file` / `upload_part`），避免整个文件先读进内存。

### 7. 生产密钥用 CAM 子账号，不要用主账号

COS 密钥只写入服务器上的 `backend/.env`（该文件不进 Git）。密钥应建 CAM 子账号并只授权单个桶的最小读写权限：

```json
{
  "version": "2.0",
  "statement": [
    {
      "effect": "allow",
      "action": ["cos:PutObject", "cos:GetObject", "cos:DeleteObject"],
      "resource": ["qcs::cos:ap-shanghai:uid/1300427458:tennis-miniapp-img-1300427458/*"]
    }
  ]
}
```

### 8. 历史文件迁移不是必须的

线上 `backend/uploads` 只有 2 个文件，数据库中对应的 URL 形如 `https://www.tennisplaynow.site:8443/uploads/<uuid>.png`。切换后：

- 旧 URL 仍然可用（`/uploads` 静态挂载保留期间）
- 若删除 `/uploads` 挂载，需先把旧文件搬到 COS 并更新数据库中的 URL

小体量场景建议：保留 `/uploads` 挂载一个版本周期，让新上传走 COS，旧链接自然过期。

### 9. 将来接入 CDN 只需改一处

CDN 相关准备已就绪：加速域名证书 `static.tennisplaynow.site`（有效期至 2026-12-26）已签发，CDN 服务已开通。备案打通后重新执行 `AddCdnDomain`（源站类型 `cos`，参数见上文脚本），然后把 `PUBLIC_BASE_URL` 或返回 URL 的前缀换成 `https://static.tennisplaynow.site` 即可，**无需迁移已有对象**，桶也不必改回私有（`CosPrivateAccess` 可与公有读共存）。

### 10. `doc/` 前缀目前同样是公开可读的（待收紧）

俱乐部认证材料（营业执照等）经 `fileType=doc` 落到 `doc/` 前缀。桶 ACL 是**桶级**公有读，前缀无法单独降权，这些文件一旦 URL 泄露即可被任何人访问。风险与切换前等价（原 `/uploads/<uuid>` 也是无鉴权静态目录），本次迁移没有让情况变差，但应当尽早收紧：

- 做法：给桶加一条 bucket policy，对 `doc/*` 拒绝匿名 `GetObject`，后端出示时改用签名 URL（`delete_object` / 签名逻辑已在 `storage.py` 中就位）
- 在收紧完成前，不要往这个桶放身份证、银行卡等强敏感材料

## 验证记录

| 时间 | 项目 | 结果 |
|---|---|---|
| 2026-09-06 | 创建桶 `tennis-miniapp-img-1300427458`（ap-shanghai，private） | 成功，`list_buckets` 可见 |
| 2026-09-27 | 开启存储桶版本控制 | `get_bucket_versioning` 返回 `Status: Enabled` |
| 2026-09-27 | 申请 DV 证书 `static.tennisplaynow.site` | 已签发，CertificateId `b7zV9lIs`，DNS_AUTO 验证通过 |
| 2026-10-07 | 桶 ACL 改为 `public-read` | `get_bucket_acl` 显示 AllUsers READ |
| 2026-10-07 | 公网匿名访问 | 测试对象返回 HTTP 200，内容正确，测试文件已清理 |
| 2026-10-07 | CDN 创建加速域名 | 失败：`ResourceUnavailable.CdnHostNoIcp`（域名备案未在腾讯云侧同步） |
| 2026-10-07 | 后端接入 COS 真实上传验证 | `avatar/<uuid>.png` 上传成功；匿名 GET 返回 HTTP 200、`Content-Type: image/png`、字节与上传一致；测试对象已删除，桶内无残留 |
| 2026-10-07 | 前端类型检查 | `npm run typecheck`（vue-tsc --noEmit）通过 |
| 2026-10-07 | 创建 CAM 子用户 `playnow-cos` + 单桶最小权限策略 | 子用户、策略（PolicyId 288832582）、永久密钥均创建成功 |
| 2026-10-07 | 子账号权限边界实测 | 上传/匿名读取/删除通过；`GetBucket` 与 `GetBucketACL` 返回 `AccessDenied`，最小权限生效 |
| 2026-10-07 | 服务器 `backend/.env` 写入 COS 配置 | 5 个键写入，原文件已备份为 `.env.bak.20261007163457` |
| 2026-10-07 | 生产部署验证（发现未上线） | 线上镜像 `d9a2e6bf...` = master，容器内无 `storage.py` / `qcloud_cos`；真实调用 `POST /api/v1/upload` 返回 `.../uploads/<uuid>.png`（本地磁盘）且文件落于 `/app/uploads/` → **代码未进 master，未上线** |
| 2026-10-07 | 本地回退路径验证（等价 CI 环境） | 无凭证时 `is_configured()=False`、`active_backend()='local'`；上传落盘后经 `/uploads` 挂载 GET 返回 200 且字节一致（复现 `http_fullflow.py` 断言）；非法前缀回落 `upload/`；`../` 越界被拦截 |
| 2026-10-07 | COS 路径回归（挂载新代码 + 生产子账号密钥的临时容器） | `is_configured()=True`、`active_backend()='cos'`；上传真实对象 → 匿名 GET `200 image/png` 字节一致 → 删除成功 |

## 当前边界

- 后端代码已切换到 COS，服务器 `backend/.env` 已写入子账号密钥（2026-10-07）。**部署状态以 `master` 的 CI 结果为准**——本文件描述的代码需先合并进 `master` 才会生效（`push → master` 触发构建与部署）。
- 存储层读写与匿名访问均已真实验证；回退路径在本地复现了 CI 断言，COS 路径在生产密钥下回归通过。
- 生产密钥为 CAM 子账号 `playnow-cos`（仅单桶三动作）；本机开发联调可用任一有权限的凭证，CI 无凭证时自动走本地磁盘回退。
- 桶内当前 0 个业务对象，历史 `backend/uploads` 文件未迁移（`/uploads` 挂载保留兼容）。
- 无 CDN 加速，外网下行按 ¥0.5/GB 计费；备案未推进，无自建资源域名、无防盗链。
- `doc/` 前缀公开可读问题尚未处理（见注意事项 10）。
