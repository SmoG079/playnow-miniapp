"""Activity media fails closed and successful uploads never touch local disk."""
from unittest.mock import Mock
import pytest
from app.services import storage


@pytest.mark.asyncio
@pytest.mark.parametrize("oversized", [False, True])
async def test_upload_size_limit_bounds_memory_and_accepts_exact_limit(monkeypatch, oversized):
    from io import BytesIO
    from fastapi import UploadFile, HTTPException
    from unittest.mock import AsyncMock
    from app import main

    monkeypatch.setattr(main.settings, "UPLOAD_MAX_MB", 1)
    limit = 1024 * 1024
    file = UploadFile(filename="test.png", file=BytesIO(b"x" * (limit + int(oversized))))
    file.read = AsyncMock(wraps=file.read)
    put = Mock(return_value="https://media.example/test.png")
    monkeypatch.setattr(storage, "put_object", put)
    try:
        if oversized:
            with pytest.raises(HTTPException) as exc:
                await main.upload_file(file, "avatar", object())
            assert exc.value.status_code == 413
            put.assert_not_called()
        else:
            assert (await main.upload_file(file, "avatar", object()))["url"] == "https://media.example/test.png"
            put.assert_called_once()
        file.read.assert_awaited_once_with(limit + 1)
    finally:
        await file.close()


def test_activity_upload_without_cos_cannot_fall_back_to_disk(monkeypatch,tmp_path):
    monkeypatch.setattr(storage,"is_configured",lambda:False)
    monkeypatch.setattr(storage,"LOCAL_DIR",str(tmp_path))
    with pytest.raises(storage.StorageUnavailable): storage.put_object("post/test.png",b"image",".png")
    assert list(tmp_path.rglob('*'))==[]


def test_activity_upload_to_cos_returns_cloud_url_without_local_copy(monkeypatch,tmp_path):
    client=Mock()
    monkeypatch.setattr(storage,"is_configured",lambda:True)
    monkeypatch.setattr(storage,"_get_client",lambda:client)
    monkeypatch.setattr(storage,"LOCAL_DIR",str(tmp_path))
    result=storage.put_object("post/test.png",b"image",".png")
    assert result==storage.public_url("post/test.png")
    client.put_object.assert_called_once_with(Bucket=storage.settings.OSS_BUCKET_NAME,Key="post/test.png",Body=b"image",ContentType="image/png")
    assert list(tmp_path.rglob('*'))==[]


def test_cos_failure_does_not_write_fallback_file(monkeypatch,tmp_path):
    client=Mock();client.put_object.side_effect=RuntimeError("COS unavailable")
    monkeypatch.setattr(storage,"is_configured",lambda:True)
    monkeypatch.setattr(storage,"_get_client",lambda:client)
    monkeypatch.setattr(storage,"LOCAL_DIR",str(tmp_path))
    with pytest.raises(RuntimeError): storage.put_object("post/test.png",b"image",".png")
    assert list(tmp_path.rglob('*'))==[]
