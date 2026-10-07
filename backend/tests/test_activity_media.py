"""Activity media fails closed and successful uploads never touch local disk."""
from unittest.mock import Mock
import pytest
from app.services import storage


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
