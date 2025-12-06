# BilibiliCookieMgmt v2 API 文档(完整)

本文档描述 v2 版本的 HTTP API, 覆盖 Cookie 资源管理、随机获取、批量检查与刷新、TV 扫码登录流程等, 并附带完整的请求与响应示例。文档基于项目代码实际实现, 默认中文说明。

## 总览

- Base URL: `http://<HOST>:<PORT>/api/v1`
  - 默认: `HOST=0.0.0.0`, `PORT=18000`(可在 `v2/config.yaml` 中修改)。
- 认证: Bearer Token(可开关)
  - 当 `API_TOKEN.enable=true` 时, 所有受保护路由需在请求头携带: `Authorization: Bearer <token>`。
  - 当 `API_TOKEN.enable=false` 时, 免认证。
- 统一错误: 
  - 认证错误: `401 Unauthorized`, 响应体 `{"detail":"无效的 Token"}` 或 `{"detail":"缺少或错误的 Authorization 头"}`。
  - 找不到资源: `404 Not Found`, 如 `{"detail":"Cookie 不存在"}` 或 `{"detail":"没有可用的 Cookie"}`。
  - 后端异常: `500 Internal Server Error` 或 `502 Bad Gateway`(下游 API 失败)。
- 健康检查: `GET /api/v1/health`, 响应 `{"status":"ok"}`。

## 数据结构约定

### Cookie 文档结构

Cookie 文件采用“两段式结构”, 文件名为 `DedeUserID.json`, 存储在 `config.STORAGE.cookie_dir`(默认 `./data/cookie`)。

示例: 

```json
{
  "raw": {
    "is_new": false,
    "mid": 123456,
    "token_info": {
      "access_token": "abcdef...",
      "refresh_token": "uvwxyz...",
      "expires_in": 2592000
    },
    "cookie_info": {
      "cookies": [
        {"name": "SESSDATA", "value": "...", "http_only": 1, "expires": 0, "secure": 1},
        {"name": "bili_jct", "value": "...", "http_only": 0, "expires": 0, "secure": 0},
        {"name": "DedeUserID", "value": "123456", "http_only": 0, "expires": 0, "secure": 0},
        {"name": "DedeUserID__ckMd5", "value": "deadbeefdeadbeef", "http_only": 0, "expires": 0, "secure": 0},
        {"name": "buvid3", "value": "...", "http_only": 0, "expires": 0, "secure": 0},
        {"name": "buvid4", "value": "...", "http_only": 0, "expires": 0, "secure": 0}
      ]
    },
    "access_token": "abcdef...",       
    "refresh_token": "uvwxyz...",       
    "expires_in": 2592000,              
    "sso": null,                        
    "hint": "login_by_tv"              
  },
  "managed": {
    "DedeUserID": "123456",
    "update_time": "2025-11-17T12:34:56.000Z",
    "last_check_time": "2025-11-17T13:00:00.000Z",
    "last_refresh_time": "2025-11-17T13:00:00.000Z",
    "refresh_status": "success",
    "error_message": null,
    "header_string": "SESSDATA=...; bili_jct=...; buvid3=...; buvid4=...; DedeUserID=123456; DedeUserID__ckMd5=deadbeefdeadbeef",
    "is_enabled": true,
    "status": "valid",
    "username": null
  }
}
```

说明: 
- `raw`: 原始响应(参考 B 站 TV 登录与刷新接口返回), 对齐原生 v2 风格: 顶层通常包含 `is_new`、`mid`、`access_token`、`refresh_token`、`expires_in`、`sso`、`hint`, 并保留 `token_info` 与 `cookie_info`。不包含 v1 的 `_cookiemgmt` 字段。
- `managed`: 系统管理信息, 含状态/时间戳/用户名/是否启用等。
  - `header_string` 的顺序固定为: `SESSDATA; bili_jct; buvid3; buvid4; DedeUserID; DedeUserID__ckMd5`, 以分号+空格分隔。
  - `status` 取值枚举: `valid`/`invalid`/`expired`/`unknown`。
  - `refresh_status` 取值枚举: `success`/`failed`/`pending`/`not_needed`。
  - `username`: 如尚未获取或值疑似为 `DedeUserID__ckMd5` 等占位, 置为 `null`。

## 认证与安全

当启用认证时(`API_TOKEN.enable=true`), 所有以下路由必须提供请求头: 

```
Authorization: Bearer <token>
```

缺失或错误将返回: 

```json
{"detail":"缺少或错误的 Authorization 头"}
```
或: 
```json
{"detail":"无效的 Token"}
```

请妥善保管 `access_token`/`refresh_token`, 避免在日志与第三方系统中泄露。

## 接口详情

### 健康检查

- 方法与路径: `GET /health`
- 响应示例: 
```json
{"status":"ok"}
```

### Cookies: 列表

- 方法与路径: `GET /cookies`
- 说明: 返回所有 Cookie 的完整文档数组(`raw` + `managed`)。
- 响应示例(仅展示一个元素, 实际为数组): 见“数据结构约定”的示例文档。

### Cookies: 详情

- 方法与路径: `GET /cookies/{DedeUserID}`
- 成功响应: 返回单个 Cookie 文档(`raw` + `managed`)。
- 失败响应: `404 Not Found`
```json
{"detail":"Cookie 不存在"}
```

### Cookies: 删除

- 方法与路径: `DELETE /cookies/{DedeUserID}`
- 成功响应: 
```json
{"deleted":true,"DedeUserID":"123456"}
```
- 失败响应: `404 Not Found`

### Cookies: 随机获取

- 方法与路径: `GET /cookies/random`
- 查询参数: 
  - `format`: `simple`(默认)或其它任意字符串(视为完整文档)。
- 选择规则: 仅在 `managed.is_enabled=true` 且 `managed.status=valid` 的候选集中随机。
- 响应示例: 
  - `format=simple`
    ```json
    {
      "DedeUserID": "123456",
      "header_string": "SESSDATA=...; bili_jct=...; buvid3=...; buvid4=...; DedeUserID=123456; DedeUserID__ckMd5=deadbeefdeadbeef"
    }
    ```
  - `format=full`(或其它)
    返回完整文档(同“数据结构约定”示例)。
- 失败响应: `404 Not Found`
```json
{"detail":"没有可用的 Cookie"}
```

### Cookies: 测试任意 Cookie 字符串有效性

- 方法与路径: `POST /cookies/test`
- 请求体: 
```json
{"cookie":"SESSDATA=...; bili_jct=...; DedeUserID=123456"}
```
- 成功响应: 
```json
{"code":0,"is_valid":true,"message":"ok"}
```
- 失败响应示例: 
```json
{"code":200,"is_valid":false,"message":"Cookie 无效"}
```
或(后端未初始化 B 站客户端): 
```json
{"code":500,"is_valid":false,"message":"Bilibili 客户端未初始化"}
```

### Cookies: 批量检查

- 方法与路径: `POST /cookies/check`
- 查询参数: 
  - `all`: 布尔, `true` 表示检查所有启用的 Cookie。
- 请求体(可选, embed 模式): 
```json
{"ids":["123456","3298631"]}
```
- 响应示例: 
```json
{
  "ok": true,
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "details": [
    {"DedeUserID":"123456","ok":true},
    {"DedeUserID":"3298631","ok":true}
  ]
}
```
- 说明: 
  - 每个成功项会同时更新对应文档的 `managed.status`、`managed.last_check_time`、可能的 `managed.username` 与 `managed.header_string`。
  - 当检查发现失效时会发送通知(若配置了 Gotify)。

### Cookies: 批量刷新

- 方法与路径: `POST /cookies/refresh`
- 查询参数: 
  - `all`: 布尔, `true` 表示刷新所有启用的 Cookie。
- 请求体(可选, embed 模式): 
```json
{"ids":["123456","3298631"]}
```
- 响应示例: 
```json
{
  "ok": true,
  "total": 1,
  "succeeded": 1,
  "failed": 0,
  "details": [
    {"DedeUserID":"123456","ok":true}
  ]
}
```
- 刷新后副作用: 
  - 更新 `raw.token_info` 与 `raw.cookie_info`；重建 `managed.header_string`。
  - 更新 `managed.update_time`、`managed.last_refresh_time`、`managed.refresh_status=success`、`managed.status=valid`、清空 `managed.error_message`。
  - 尝试获取并写入 `buvid3/buvid4`, 随后触发健康检查与发送成功通知。
  - 刷新失败时更新 `managed.refresh_status=failed` 与 `managed.error_message`。

### Cookies: 启用/禁用

- 方法与路径: `PATCH /cookies/{DedeUserID}/enabled`
- 请求体: 
```json
{"is_enabled":true}
```
- 成功响应: 返回更新后的完整文档。
- 说明: 该开关仅影响 `GET /cookies/random` 的候选集；检查与刷新接口不受此开关影响。

### TV 扫码登录: 生成二维码

- 方法与路径: `GET /auth/tv/qrcode`
- 成功响应: 
```json
{"auth_code":"abcd1234","qrcode_url":"https://..."}
```
- 失败响应: `502 Bad Gateway`
```json
{"detail":"生成二维码失败"}
```

### TV 扫码登录: 轮询状态

- 方法与路径: `GET /auth/tv/poll`
- 查询参数: 
  - `auth_code`: `tv/qrcode` 返回的 `auth_code`。
- 成功响应(登录成功时): 返回保存后的 Cookie 文档(即“两段式结构”)。
- 其它状态示例: 
```json
{"code":86090,"message":"等待扫码"}
```
或: 
```json
{"code":86038,"message":"二维码已失效"}
```
- 说明: 
  - 当 `code==0`(登录成功)时, 系统会自动调用 `create_from_raw` 保存文档, 并执行一次后置处理: 尝试获取 buvid3/4、执行首轮有效性检查与用户名写入。

## cURL 示例

以下示例假定启用了认证, Token 为 `my-token`: 

- 随机获取(简化格式): 
```
curl -H "Authorization: Bearer my-token" \
     "http://localhost:18000/api/v1/cookies/random?format=simple"
```

- 批量检查(指定两个 ID): 
```
curl -X POST -H "Authorization: Bearer my-token" -H "Content-Type: application/json" \
     -d '{"ids":["123456","3298631"]}' \
     "http://localhost:18000/api/v1/cookies/check"
```

- 刷新所有启用的 Cookie: 
```
curl -X POST -H "Authorization: Bearer my-token" \
     "http://localhost:18000/api/v1/cookies/refresh?all=true"
```

- 设置启用: 
```
curl -X PATCH -H "Authorization: Bearer my-token" -H "Content-Type: application/json" \
     -d '{"is_enabled":true}' \
     "http://localhost:18000/api/v1/cookies/123456/enabled"
```

## 行为与差异说明(相对 v1)

- 路径与参数: 
  - v1: `/api/cookie/random?type=sim`；v2: `/api/v1/cookies/random?format=simple`。
  - v1 简化返回为单行字符串；v2 简化返回为结构体 `{DedeUserID, header_string}`。
- 状态与过滤: 
  - v1 依赖 `_cookiemgmt.cookie_valid/enabled`；v2 使用 `managed.status/is_enabled`。
- 头串格式: 
  - v1 顺序通常为 `DedeUserID`、`SESSDATA`、`bili_jct` 等；v2 固定顺序为 `SESSDATA; bili_jct; buvid3; buvid4; DedeUserID; DedeUserID__ckMd5`。
- 错误语义: 
  - v1 习惯返回 `{code, message}`；v2 更规范地使用 HTTP 状态码(同时部分工具型接口仍返回 `{code, message}` 字段用于便捷判断)。

## 备注与最佳实践

- 建议在保存与刷新后, 保留 `raw.access_token/refresh_token` 的顶层镜像字段, 便于客户端读取；同时以 `raw.token_info` 为权威来源进行刷新。
- 保留 `raw.cookie_info.cookies` 的完整列表, 确保外部工具可复原特定 Cookie 项(如 `buvid3/4`)。
- `managed.username` 缺失或不可信时使用 `null`, 避免将 `ckMd5` 等占位串误认为用户名。
- 启用 Gotify 后, 失效与刷新成功事件将发送通知, 便于运维监控。

—— 完 ———