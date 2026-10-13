import json
import logging
import time
from functools import lru_cache

from wechatpayv3 import WeChatPay, WeChatPayType

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class WeChatPayError(RuntimeError):
    """微信支付接口返回非 2xx 响应。

    ``status`` 是 HTTP 状态码，``payload`` 是微信返回的错误体（含 ``code``）。
    """

    def __init__(self, status: int, payload: dict):
        self.status = status
        self.payload = payload or {}
        super().__init__(self.payload.get("code") or f"WeChat Pay HTTP {status}")


def wx_request(wxpay: WeChatPay, method: str, **kwargs) -> dict:
    """调用微信支付 SDK 方法，并把返回值统一解析为 dict。

    SDK 的 ``core.request`` 一律返回 ``(http_status, text)`` 元组，但调用方极易
    误当成 dict 直接使用（``resp.get(...)`` 抛 AttributeError，被上层 ``except``
    吞掉后表现为"退款/分账静默失败"，甚至把已退款的订单错误回退）。所有调用都
    应经由此处解包。

    非 2xx 抛 :class:`WeChatPayError`，由调用方按业务语义决定重试还是重新提交；
    网络异常正常向上抛出，交给既有的可重试判定处理。
    """
    response = getattr(wxpay, method)(**kwargs)
    if isinstance(response, tuple):
        status, body = response
        payload = json.loads(body) if body else {}
        if status >= 300:
            raise WeChatPayError(status, payload)
        return payload
    if not isinstance(response, dict):
        raise RuntimeError(f"Unexpected WeChat Pay response from {method}")
    return response


def _generate_nonce(length: int = 32) -> str:
    import secrets
    return secrets.token_hex(length // 2)


def build_jsapi_params(wxpay: WeChatPay, prepay_id: str) -> dict:
    """Build parameters for wx.requestPayment from a WeChat prepay_id."""
    settings = get_settings()
    appid = settings.WX_APP_ID
    timestamp = str(int(time.time()))
    nonce_str = _generate_nonce()
    package = f"prepay_id={prepay_id}"
    pay_sign = wxpay.sign([appid, timestamp, nonce_str, package])
    return {
        "timeStamp": timestamp,
        "nonceStr": nonce_str,
        "package": package,
        "signType": "RSA",
        "paySign": pay_sign,
    }


def _load_pay_public_key(settings) -> tuple[str | None, str | None]:
    """读取「微信支付公钥」用于验签。

    微信已下架平台证书（``GET /v3/certificates`` 对新商户返回
    ``RESOURCE_NOT_EXISTS``），SDK 默认会在构造时引导平台证书并因此抛
    ``No wechatpay platform certificate``。配置了公钥后 SDK 走公钥模式：
    不再下载平台证书，回调验签按 ``Wechatpay-Serial`` 匹配 ``public_key_id``。
    """
    path = (settings.WX_PAY_PUBLIC_KEY_PATH or "").strip()
    key_id = (settings.WX_PAY_PUBLIC_KEY_ID or "").strip()
    if not path or not key_id:
        return None, None
    with open(path, "r", encoding="utf-8") as f:
        return f.read(), key_id


@lru_cache()
def get_wxpay() -> WeChatPay:
    """Return a cached WeChatPay V3 client configured from settings.

    The client is used to verify callback signatures and decrypt notifications.
    Platform certificates are downloaded/cached automatically when cert_dir is set.
    """
    settings = get_settings()
    required = [
        settings.WX_MCH_ID,
        settings.WX_MCH_API_V3_KEY,
        settings.WX_MCH_SERIAL_NO,
        settings.WX_MCH_PRIVATE_KEY_PATH,
    ]
    if not all(required):
        raise RuntimeError("WeChat Pay configuration is incomplete")

    with open(settings.WX_MCH_PRIVATE_KEY_PATH, "r", encoding="utf-8") as f:
        private_key = f.read()

    public_key, public_key_id = _load_pay_public_key(settings)
    if not public_key:
        logger.warning(
            "WeChat Pay public key (WX_PAY_PUBLIC_KEY_ID/PATH) is not configured; "
            "falling back to platform certificates, which WeChat no longer issues "
            "to new merchants."
        )

    return WeChatPay(
        wechatpay_type=WeChatPayType.MINIPROG,
        mchid=settings.WX_MCH_ID,
        private_key=private_key,
        cert_serial_no=settings.WX_MCH_SERIAL_NO,
        appid=settings.WX_APP_ID,
        apiv3_key=settings.WX_MCH_API_V3_KEY,
        notify_url=settings.WX_PAY_NOTIFY_URL or None,
        cert_dir=None if public_key else (settings.WX_PAY_CERT_DIR or None),
        public_key=public_key,
        public_key_id=public_key_id,
        logger=None,  # SDK debug output contains full sensitive callback resources.
    )
