# WBI 签名

自 2023 年 3 月起, Bilibili Web 端部分接口开始采用 WBI 签名鉴权, 表现在 REST API 请求时在 Query param 中添加了 `w_rid` 和 `wts` 字段。WBI 签名鉴权独立于 [APP 鉴权](APP.md) 与其他 Cookie 鉴权, 目前被认为是一种 Web 端风控手段。

经持续观察, 大部分查询性接口都已经或准备采用 WBI 签名鉴权, 请求 WBI 签名鉴权接口时, 若签名参数 `w_rid` 与时间戳 `wts` 缺失、错误, 会返回 [`v_voucher`](v_voucher.md), 如: 

```json
{"code":0,"message":"0","ttl":1,"data":{"v_voucher":"voucher_******"}}
```

感谢 [#631](https://github.com/SocialSisterYi/bilibili-API-collect/issues/631) 的研究与逆向工程。

细节更新: [#885](https://github.com/SocialSisterYi/bilibili-API-collect/issues/885)。

最新进展: [#919](https://github.com/SocialSisterYi/bilibili-API-collect/issues/919)

## WBI 签名算法

1. 获取实时口令 `img_key`、`sub_key`

   从 [nav 接口](../../login/login_info.md#导航栏用户信息) 中获取 `img_url`、`sub_url` 两个字段的参数。
   或从 [bili_ticket 接口](bili_ticket.md#接口) 中获取 `img` `sub` 两个字段的参数。

   **注: `img_url`、`sub_url` 两个字段的值看似为存于 BFS 中的 png 图片 url, 实则只是经过伪装的实时 Token, 故无需且不能试图访问这两个 url**

   ```json
   {"code":-101,"message":"账号未登录","ttl":1,"data":{"isLogin":false,"wbi_img":{"img_url":"https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png","sub_url":"https://i0.hdslb.com/bfs/wbi/4932caff0ff746eab6f01bf08b70ac45.png"}}}
   ```

   截取其文件名, 分别记为 `img_key`、`sub_key`, 如上述例子中的 `7cd084941338484aae1ad9425b84077c` 和 `4932caff0ff746eab6f01bf08b70ac45`。

   `img_key`、`sub_key` 全站统一使用, 观测知应为**每日更替**, 使用时建议做好**缓存和刷新**处理。

   特别地, 发现部分接口将 `img_key`、`sub_key` 硬编码进 JavaScript 文件内, 如搜索接口 `https://s1.hdslb.com/bfs/static/laputa-search/client/assets/index.1ea39bea.js`, 暂不清楚原因及影响。
   同时, 部分页面会在 SSR 的 `__INITIAL_STATE__` 包含 `wbiImgKey` 与 `wbiSubKey`, 具体可用性与区别尚不明确

2. 打乱重排实时口令获得 `mixin_key`

   把上一步获取到的 `sub_key` 拼接在 `img_key` 后面(下例记为 `raw_wbi_key`), 遍历重排映射表 `MIXIN_KEY_ENC_TAB`, 取出 `raw_wbi_key` 中对应位置的字符拼接得到新的字符串, 截取前 32 位, 即为 `mixin_key`。

   重排映射表 `MIXIN_KEY_ENC_TAB` 长为 64, 内容如下: 

   ```rust
   const MIXIN_KEY_ENC_TAB: [u8; 64] = [
       46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
       33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
       61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
       36, 20, 34, 44, 52
   ]
   ```

   重排操作如下例: 

   ```rust
    fn gen_mixin_key(raw_wbi_key: impl AsRef<[u8]>) -> String {
        const MIXIN_KEY_ENC_TAB: [u8; 64] = [
            46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49, 33, 9, 42,
            19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60,
            51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
        ];
        let raw_wbi_key = raw_wbi_key.as_ref();
        let mut mixin_key = {
            let binding = MIXIN_KEY_ENC_TAB
                .iter()
                // 此步操作即遍历 MIXIN_KEY_ENC_TAB, 取出 raw_wbi_key 中对应位置的字符
                .map(|n| raw_wbi_key[*n as usize])
                // 并收集进数组内
                .collect::<Vec<u8>>();
            unsafe { String::from_utf8_unchecked(binding) }
        };
        let _ = mixin_key.split_off(32); // 截取前 32 位字符
        mixin_key
    }
   ```

   如 `img_key` -> `7cd084941338484aae1ad9425b84077c`、`sub_key` -> `4932caff0ff746eab6f01bf08b70ac45` 经过上述操作后得到 `mixin_key` -> `ea1db124af3c7062474693fa704f4ff8`。

3. 计算签名(即 `w_rid`)

   若下方内容为欲签名的**原始**请求参数(以 JavaScript Object 为例)

   ```javascript
   {
     foo: '114',
     bar: '514',
     zab: 1919810
   }
   ```

   `wts` 字段的值应为当前以秒为单位的 Unix 时间戳, 如 `1702204169`

   复制一份参数列表, 添加 `wts` 参数, 即: 

   ```javascript
   {
        foo: '114',
        bar: '514',
        zab: 1919810,
        wts: 1702204169
   }
   ```

   随后按键名升序排序后百分号编码 URL Query, 拼接前面得到的 `mixin_key`, 如 `bar=514&foo=114&wts=1702204169&zab=1919810ea1db124af3c7062474693fa704f4ff8`, 计算其 MD5 即为 `w_rid`。

   需要注意的是: 如果参数值含中文或特殊字符等, 编码字符字母应当**大写** (部分库会错误编码为小写字母), 空格应当编码为 `%20`(部分库按 `application/x-www-form-urlencoded` 约定编码为 `+`), 具体正确行为可参考 [encodeURIComponent 函数](https://tc39.es/ecma262/multipage/global-object.html#sec-encodeuricomponent-uricomponent)

   例如: 

   ```javascript
   {
     foo: 'one one four',
     bar: '五一四',
     baz: 1919810
   }
   ```

    应该被编码为 `bar=%E4%BA%94%E4%B8%80%E5%9B%9B&baz=1919810&foo=one%20one%20four`。

4. 向原始请求参数中添加 `w_rid`、`wts` 字段

   将上一步得到的 `w_rid` 以及前面的 `wts` 追加到**原始**请求参数编码得到的 URL Query 后即可, 目前看来无需对原始请求参数排序。

   如前例最终得到 `bar=514&foo=114&zab=1919810&w_rid=8f6f2b5b3d485fe1886cec6a0be8c5d4&wts=1702204169`。

## Demo

含 [Python](#python)、[JavaScript](#javascript)、[Golang](#golang)、[C#](#csharp)、[Java](#java)、[Kotlin](#kotlin)、[Swift](#swift)、[C++](#cplusplus)、[Rust](#rust)、[Haskell](#haskell) 语言编写的 Demo

### Python

需要`requests`依赖

```python
from functools import reduce
from hashlib import md5
import urllib.parse
import time
import requests

mixinKeyEncTab = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52
]

def getMixinKey(orig: str):
    '对 imgKey 和 subKey 进行字符顺序打乱编码'
    return reduce(lambda s, i: s + orig[i], mixinKeyEncTab, '')[:32]

def encWbi(params: dict, img_key: str, sub_key: str):
    '为请求参数进行 wbi 签名'
    mixin_key = getMixinKey(img_key + sub_key)
    curr_time = round(time.time())
    params['wts'] = curr_time                                   # 添加 wts 字段
    params = dict(sorted(params.items()))                       # 按照 key 重排参数
    # 过滤 value 中的 "!'()*" 字符
    params = {
        k : ''.join(filter(lambda chr: chr not in "!'()*", str(v)))
        for k, v 
        in params.items()
    }
    query = urllib.parse.urlencode(params)                      # 序列化参数
    wbi_sign = md5((query + mixin_key).encode()).hexdigest()    # 计算 w_rid
    params['w_rid'] = wbi_sign
    return params

def getWbiKeys() -> tuple[str, str]:
    '获取最新的 img_key 和 sub_key'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
        'Referer': 'https://www.bilibili.com/'
    }
    resp = requests.get('https://api.bilibili.com/x/web-interface/nav', headers=headers)
    resp.raise_for_status()
    json_content = resp.json()
    img_url: str = json_content['data']['wbi_img']['img_url']
    sub_url: str = json_content['data']['wbi_img']['sub_url']
    img_key = img_url.rsplit('/', 1)[1].split('.')[0]
    sub_key = sub_url.rsplit('/', 1)[1].split('.')[0]
    return img_key, sub_key

img_key, sub_key = getWbiKeys()

signed_params = encWbi(
    params={
        'foo': '114',
        'bar': '514',
        'baz': 1919810
    },
    img_key=img_key,
    sub_key=sub_key
)
query = urllib.parse.urlencode(signed_params)
print(signed_params)
print(query)
```

输出内容分别是进行 Wbi 签名的后参数的 key-Value 以及 url query 形式

```
{'bar': '514', 'baz': '1919810', 'foo': '114', 'wts': '1702204169', 'w_rid': 'd3cbd2a2316089117134038bf4caf442'}
bar=514&baz=1919810&foo=114&wts=1702204169&w_rid=d3cbd2a2316089117134038bf4caf442
```