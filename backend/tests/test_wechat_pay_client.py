"""微信支付客户端构造契约：平台证书已下线，必须走「微信支付公钥」模式。

2026-10-13 实测：``GET /v3/certificates`` 对该商户返回

    {"code":"RESOURCE_NOT_EXISTS",
     "message":"无可用的平台证书，请在商户平台-API安全申请使用微信支付公钥"}

SDK 构造时会因此抛 ``No wechatpay platform certificate``，支付相关接口全部
5xx。正确做法是配置 ``WX_PAY_PUBLIC_KEY_PATH`` + ``WX_PAY_PUBLIC_KEY_ID``，
让 SDK 跳过平台证书引导、改用公钥验签。

这里只锁定配置装配契约，不真连微信（``WeChatPay`` 被替换成桩）。
"""
import pytest

from app.core import wechat_pay

MCH_ID = "1751659629"
SERIAL_NO = "119A6032DB3CDAFEA3CB7CB18E6AB40382EBC3CE"
PRIVATE_KEY_BODY = "PRIVATE-KEY-BODY"
PUBLIC_KEY_BODY = "PUBLIC-KEY-BODY"


@pytest.fixture
def pay_env(tmp_path, monkeypatch):
    """准备一份完整的商户配置（不含公钥），并清掉 get_wxpay 的缓存。"""
    key_file = tmp_path / "apiclient_key.pem"
    key_file.write_text(PRIVATE_KEY_BODY, encoding="utf-8")
    pub_file = tmp_path / "pub_key.pem"
    pub_file.write_text(PUBLIC_KEY_BODY, encoding="utf-8")

    settings = wechat_pay.get_settings()
    monkeypatch.setattr(settings, "WX_MCH_ID", MCH_ID)
    monkeypatch.setattr(settings, "WX_MCH_API_V3_KEY", "x" * 32)
    monkeypatch.setattr(settings, "WX_MCH_SERIAL_NO", SERIAL_NO)
    monkeypatch.setattr(settings, "WX_MCH_PRIVATE_KEY_PATH", str(key_file))
    monkeypatch.setattr(settings, "WX_APP_ID", "wxe6fd99528373b676")
    monkeypatch.setattr(settings, "WX_PAY_CERT_DIR", "/app/pay-certs")
    monkeypatch.setattr(settings, "WX_PAY_NOTIFY_URL", "https://example.test/notify")
    monkeypatch.setattr(settings, "WX_PAY_PUBLIC_KEY_PATH", "")
    monkeypatch.setattr(settings, "WX_PAY_PUBLIC_KEY_ID", "")

    wechat_pay.get_wxpay.cache_clear()
    yield settings, pub_file
    wechat_pay.get_wxpay.cache_clear()


def _capture_client(monkeypatch) -> dict:
    """把 SDK 客户端换成只记录参数的桩，返回 capture dict。"""
    captured: dict = {}

    def fake_wechat_pay(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(wechat_pay, "WeChatPay", fake_wechat_pay)
    return captured


def test_load_pay_public_key_requires_both_fields(pay_env, monkeypatch):
    """公钥路径与公钥 ID 缺任一即视为未配置。"""
    settings, pub_file = pay_env

    assert wechat_pay._load_pay_public_key(settings) == (None, None)

    monkeypatch.setattr(settings, "WX_PAY_PUBLIC_KEY_ID", "PUB_KEY_ID_TEST")
    assert wechat_pay._load_pay_public_key(settings) == (None, None)

    monkeypatch.setattr(settings, "WX_PAY_PUBLIC_KEY_PATH", str(pub_file))
    monkeypatch.setattr(settings, "WX_PAY_PUBLIC_KEY_ID", "")
    assert wechat_pay._load_pay_public_key(settings) == (None, None)


def test_public_key_mode_disables_platform_certificate_lookup(pay_env, monkeypatch):
    """配好公钥后：透传公钥与公钥 ID，且不再依赖 cert_dir 下载平台证书。"""
    settings, pub_file = pay_env
    monkeypatch.setattr(settings, "WX_PAY_PUBLIC_KEY_PATH", str(pub_file))
    monkeypatch.setattr(settings, "WX_PAY_PUBLIC_KEY_ID", "PUB_KEY_ID_TEST")
    captured = _capture_client(monkeypatch)

    wechat_pay.get_wxpay()

    assert captured["public_key"] == PUBLIC_KEY_BODY
    assert captured["public_key_id"] == "PUB_KEY_ID_TEST"
    assert captured["cert_dir"] is None
    assert captured["cert_serial_no"] == SERIAL_NO
    assert captured["mchid"] == MCH_ID


def test_falls_back_to_cert_dir_without_public_key(pay_env, monkeypatch):
    """未配置公钥时保留旧行为：沿用 cert_dir（此时微信会拒绝签发平台证书）。"""
    settings, _ = pay_env
    captured = _capture_client(monkeypatch)

    wechat_pay.get_wxpay()

    assert captured["public_key"] is None
    assert captured["public_key_id"] is None
    assert captured["cert_dir"] == "/app/pay-certs"


def test_incomplete_merchant_config_raises(pay_env, monkeypatch):
    """商户四件套缺一即拒绝构造，避免带着半截配置去调微信。"""
    settings, _ = pay_env
    monkeypatch.setattr(settings, "WX_MCH_SERIAL_NO", "")

    with pytest.raises(RuntimeError, match="incomplete"):
        wechat_pay.get_wxpay()
