"""Tencent WebService parameters. Credentials are kept on the backend only."""
from hashlib import md5

GEOCODER_PATH = "/ws/geocoder/v1/"
GEOCODER_URL = "https://apis.map.qq.com" + GEOCODER_PATH


def service_params(path: str, values: dict, key: str, secret: str = "") -> dict:
    params = {**values, "key": key}
    if secret:
        # Tencent signs the exact path and sorted, unencoded parameter values.
        query = "&".join(f"{name}={params[name]}" for name in sorted(params))
        content = f"{path}?{query}{secret}"
        params["sig"] = md5(content.encode("utf-8"), usedforsecurity=False).hexdigest()
    return params


def geocoder_params(values: dict, key: str, secret: str = "") -> dict:
    return service_params(GEOCODER_PATH, values, key, secret)
