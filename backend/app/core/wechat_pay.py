import logging
import time
from functools import lru_cache

from wechatpayv3 import WeChatPay, WeChatPayType

from app.core.config import get_settings

logger = logging.getLogger(__name__)


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

    return WeChatPay(
        wechatpay_type=WeChatPayType.MINIPROG,
        mchid=settings.WX_MCH_ID,
        private_key=private_key,
        cert_serial_no=settings.WX_MCH_SERIAL_NO,
        appid=settings.WX_APP_ID,
        apiv3_key=settings.WX_MCH_API_V3_KEY,
        notify_url=settings.WX_PAY_NOTIFY_URL or None,
        cert_dir=settings.WX_PAY_CERT_DIR or None,
        logger=logger,
    )
