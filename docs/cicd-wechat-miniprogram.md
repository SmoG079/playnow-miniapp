# PlayNow CI/CD: WeChat Mini Program Experience Upload

This project keeps backend deployment and mini program experience upload in one GitHub Actions pipeline.

## Pipeline

The workflow is `.github/workflows/deploy.yml`.

On every push to `master`:

1. `backend-test`
   - installs backend dependencies
   - compiles backend Python files
   - runs free-post query tests and selected pytest suites

2. `miniprogram-check`
   - installs root Node dependencies with `npm ci`
   - runs native mini program regression tests
   - validates upload configuration with a dry run

3. `backend-build-and-deploy`
   - builds `backend/Dockerfile`
   - pushes `ghcr.io/smog079/playnow-miniapp-api:latest`
   - pushes `ghcr.io/smog079/playnow-miniapp-api:<commit-sha>`
   - SSHes to the Tencent Cloud server
   - pulls and restarts compose services
   - runs `alembic upgrade head`
   - checks `http://127.0.0.1:8000/health`

4. `miniprogram-upload`
   - runs only after mini program checks and backend deploy pass
   - uploads a WeChat experience version with `miniprogram-ci`
   - does not submit for review or publish production

Manual workflow dispatch can skip the mini program upload by selecting `upload_miniprogram=false`.

## GitHub Secrets

Backend deployment secrets:

- `SERVER_HOST`
- `SERVER_USER`
- `SERVER_SSH_KEY`
- `SERVER_PORT`
- `SERVER_PROJECT_PATH`

WeChat mini program upload secrets:

- `WX_MINIPROGRAM_PRIVATE_KEY`
- `WX_MINIPROGRAM_PRIVATE_KEY_BASE64`
- `WX_MINIPROGRAM_ROBOT`

Use either `WX_MINIPROGRAM_PRIVATE_KEY` or `WX_MINIPROGRAM_PRIVATE_KEY_BASE64`.

`WX_MINIPROGRAM_PRIVATE_KEY` can be the raw PEM key. If the UI stores escaped line breaks, `\n` is supported.

`WX_MINIPROGRAM_PRIVATE_KEY_BASE64` is safer for copy/paste:

```bash
base64 -w 0 private.key
```

On Windows PowerShell:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes(".\private.key"))
```

`WX_MINIPROGRAM_ROBOT` is optional. If unset, robot `1` is used.

## Tencent Cloud Server Prerequisites

The deployment directory in `SERVER_PROJECT_PATH` must already contain:

- `docker-compose.yml`
- `docker-compose.prod.yml`
- `backend/.env`
- nginx config and SSL files referenced by compose

The server needs:

- Docker Engine
- Docker Compose plugin
- network access to `ghcr.io`
- inbound ports already configured in Tencent Cloud security groups
- a user that can run Docker commands

## WeChat Prerequisites

In WeChat Mini Program admin console:

- enable mini program code upload key
- download the upload private key
- confirm AppID `wxfad430ba15c6c3e2`
- keep legal request/upload/download domains configured

The workflow uploads an experience version only. Review submission and production release remain manual until account permissions and release policy are confirmed.

## Local Commands

Validate mini program checks without uploading:

```bash
npm run check:miniprogram
```

Upload locally when a private key is available:

```bash
WX_MINIPROGRAM_PRIVATE_KEY_BASE64=... npm run upload:miniprogram
```

The upload script is `scripts/upload-miniprogram.cjs`.

## Current Boundaries

- Real WeChat Pay is intentionally not enabled yet.
- The booking confirmation page still keeps the temporary payment success flow.
- The backend migration step is included because free match posts require nullable `match_posts.club_id`.
- Experience upload does not prove iOS/Android real-device acceptance; it only makes the build available for tester scanning.
