import hashlib
import urllib.parse
from .constants import APP_KEY, APP_SEC


def tvsign(params, appkey=APP_KEY, appsec=APP_SEC):
    """TV签名函数"""
    params.update({"appkey": appkey})
    params = dict(sorted(params.items()))
    query = urllib.parse.urlencode(params)
    sign = hashlib.md5((query + appsec).encode()).hexdigest()
    params.update({"sign": sign})
    return params