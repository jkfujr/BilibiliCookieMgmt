# Bilibili Cookie Management V2 API 文档

> **Linus 的架构审查 (Deep Thinking Analysis)**
>
> **1. 设计哲学：实用主义至上**
> V2 API 的设计明显遵循了"解决实际问题"的原则。
> - **批量操作**：`check` 和 `refresh` 接口支持 `all=true` 或指定 `ids` 列表。这是对现实场景的深刻理解——用户不仅需要操作单个 Cookie，更常需要批量维护。这消除了前端发起 N 次请求的愚蠢做法。
> - **混合存储结构**：数据返回保留了 `raw` (Bilibili 原始响应) 和 `managed` (内部管理状态)。这体现了"不丢失信息"的智慧。如果 Bilibili 的 API 变动，原始数据可能包含未来需要的字段，这种宽容的存储策略是明智的。
>
> **2. 优良品味 (Good Taste)**
> - **RESTful 路径**：资源路径清晰 (`/cookies/{id}`)，动作路径明确 (`/refresh`, `/check`)。没有为了教条而强行把动作映射到 PUT/POST 上，而是使用了直观的动词路径，这是好品味。
> - **幂等性**：`check` 和 `refresh` 操作本质上是幂等的，多次调用不会破坏系统状态（只会更新状态）。
>
> **3. 潜在改进点 (Room for Improvement)**
> - **分页缺失**：`/cookies/` 返回所有数据。如果只有几十个账号，这很完美（简单即正义）。如果有 1万个账号，这就是灾难。但在当前单机工具的定位下，引入分页可能属于"过度设计"。
> - **轮询接口响应不一致**：`/auth/tv/poll` 在成功时返回 Document 对象，在未完成时返回 `{code, message}`。类型系统纯粹主义者会尖叫，但对于动态语言编写的脚本小子来说，这很方便。
>
> **结论**：这是一个坚固、务实且目标明确的 API 设计。它没有陷入企业级架构的泥潭，而是直接切入痛点。

---

## 1. 概览 (Overview)

- **Base URL**: `/api/v1`
- **认证**: 所有接口需要在 Header 中携带 API Token (如果配置中开启)。
  - Header: `Authorization: Bearer <your_token>`
- **数据格式**: JSON

## 2. 认证模块 (Auth)

### 2.1 生成 TV 扫码二维码
获取 Bilibili TV 端扫码登录的二维码信息。

- **URL**: `/auth/tv/qrcode`
- **Method**: `GET`
- **响应示例**:
```json
{
  "auth_code": "x1234567890...",
  "qrcode_url": "https://passport.bilibili.com/h5-app/passport/login/scan?..."
}
```

### 2.2 轮询扫码状态
检查用户是否已扫码并确认登录。

- **URL**: `/auth/tv/poll`
- **Method**: `GET`
- **Query 参数**:
  - `auth_code` (必填): 从生成二维码接口获取的 auth_code。
- **响应说明**:
  - **登录成功**: 返回完整的 Cookie 文档结构（包含 `raw` 和 `managed` 字段）。
  - **未成功**: 返回状态码和消息。
- **响应示例 (等待扫码/失效)**:
```json
{
  "code": 86090,
  "message": "等待扫码"
}
```
- **响应示例 (成功)**:
```json
{
  "raw": { ... },
  "managed": {
    "DedeUserID": "123456",
    "status": "valid",
    "username": "bili_user",
    ...
  }
}
```

---

## 3. Cookie 管理模块 (Cookies)

### 3.1 获取 Cookie 列表
返回所有已存储的 Cookie 文档。

- **URL**: `/cookies/`
- **Method**: `GET`
- **响应示例**:
```json
[
  {
    "managed": {
      "DedeUserID": "123456",
      "status": "valid",
      "is_enabled": true,
      "last_check_time": "2025-01-01T12:00:00",
      ...
    },
    "raw": { ... }
  },
  ...
]
```

### 3.2 获取单个 Cookie
- **URL**: `/cookies/{DedeUserID}`
- **Method**: `GET`
- **Path 参数**:
  - `DedeUserID`: Bilibili 用户 ID
- **响应**: 单个 Cookie 文档对象。

### 3.3 删除 Cookie
- **URL**: `/cookies/{DedeUserID}`
- **Method**: `DELETE`
- **响应示例**:
```json
{
  "deleted": true,
  "DedeUserID": "123456"
}
```

### 3.4 获取随机可用 Cookie
用于爬虫或其它服务获取一个可用的 Cookie。

- **URL**: `/cookies/random`
- **Method**: `GET`
- **Query 参数**:
  - `format`: `simple` (默认) 或 `full`。
- **响应示例 (simple)**:
```json
{
  "DedeUserID": "123456",
  "header_string": "SESSDATA=...; bili_jct=...; DedeUserID=123456; ..."
}
```

### 3.5 批量/指定检查有效性
触发后台检查 Cookie 是否有效。

- **URL**: `/cookies/check`
- **Method**: `POST`
- **Query 参数**:
  - `all`: `true` / `false` (默认 false)。若为 true，忽略 ids 参数，检查所有启用账号。
- **Body 参数**:
```json
{
  "ids": ["123456", "234567"]  // 可选，指定要检查的 ID 列表
}
```
- **响应示例**:
```json
{
  "ok": true,
  "total": 2,
  "succeeded": 1,
  "failed": 1,
  "details": [
    { "DedeUserID": "123456", "ok": true },
    { "DedeUserID": "234567", "ok": false, "message": "Cookie 无效" }
  ]
}
```

### 3.6 批量/指定刷新 Cookie
触发后台刷新 Cookie 操作（使用 Refresh Token 换取新 Cookie）。

- **URL**: `/cookies/refresh`
- **Method**: `POST`
- **Query 参数**:
  - `all`: `true` / `false`。
- **Body 参数**:
```json
{
  "ids": ["123456"]
}
```
- **响应示例**: 结构同 `check` 接口。

### 3.7 设置启用/禁用状态
禁用后的 Cookie 不会被 `random` 接口选中。

- **URL**: `/cookies/{DedeUserID}/enabled`
- **Method**: `PATCH`
- **Body 参数**:
```json
{
  "is_enabled": false
}
```
- **响应**: 更新后的 Cookie 文档。

### 3.8 测试 Cookie 字符串
测试一段原始 Cookie 字符串是否有效。

- **URL**: `/cookies/test`
- **Method**: `POST`
- **Body 参数**:
```json
{
  "cookie": "SESSDATA=xxx; ..."
}
```
- **响应示例**:
```json
{
  "code": 0,
  "is_valid": true,
  "message": "ok"
}
```

---

## 4. 数据模型 (Models)

### ManagedInfo (管理信息)
存储在 `managed` 字段下的核心状态信息。

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `DedeUserID` | string | 用户 ID (主键) |
| `status` | string | `valid` (有效), `invalid` (失效), `expired` (过期), `unknown` (未知) |
| `is_enabled` | bool | 是否启用 |
| `username` | string | 用户昵称 |
| `header_string` | string | 拼接好的 HTTP Cookie 请求头字符串 |
| `update_time` | string | 最后更新时间 (ISO8601) |
| `last_check_time` | string | 最后检查时间 |
| `last_refresh_time` | string | 最后刷新时间 |
| `refresh_status` | string | 刷新结果状态: `success`, `failed`, `not_needed` |
| `error_message` | string | 最近一次检查或刷新的错误信息 |
