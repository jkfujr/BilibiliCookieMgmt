# BilibiliCookieMgmt API 文档

本文档描述了 BilibiliCookieMgmt 项目的所有 API 接口。

## 基础信息

- **Base URL**: `http://localhost:8000`
- **认证方式**: API Token（通过 Header 传递）
- **Content-Type**: `application/json`

## 认证说明

大部分 API 需要在请求头中包含 API Token：

```
token: your_api_token
```

当服务器配置启用 API Token 验证时，此参数为必填项。

---

## 1. 主页路由 (main.py)

### 1.1 获取首页

**接口路径**: `GET /`

**功能描述**: 返回静态首页文件

**请求参数**: 无

**响应**: 返回 `static/index.html` 文件

---

## 2. 认证相关 API (auth.py)

### 2.1 生成二维码

**接口路径**: `GET /api/passport-login/web/qrcode/generate`

**功能描述**: 生成用于扫码登录的二维码

**请求参数**:
- **Headers**:
  - `token` (string, 可选*): API Token

**成功响应**:
```json
{
  "code": 0,
  "data": {
    "url": "二维码URL",
    "auth_code": "认证码"
  }
}
```

**错误响应**:
- `401`: 认证失败
- `500`: 服务器错误

### 2.2 轮询扫码状态

**接口路径**: `GET /api/passport-login/web/qrcode/poll`

**功能描述**: 轮询二维码扫码状态

**请求参数**:
- **Query Parameters**:
  - `auth_code` (string, 必填): 认证码
- **Headers**:
  - `token` (string, 可选*): API Token

**成功响应**:
```json
{
  "code": 0,
  "message": "扫码成功",
  "data": {
    "cookie_info": {
      "cookies": [
        {
          "name": "cookie名称",
          "value": "cookie值"
        }
      ]
    },
    "token_info": {
      "access_token": "访问令牌",
      "refresh_token": "刷新令牌",
      "expires_in": 过期时间秒数
    }
  }
}
```

**其他响应**:
- `86038`: 二维码已失效
- `86090`: 等待扫码
- `500`: 服务器错误

---

## 3. Cookie 管理 API (cookie.py)

### 3.1 获取 Cookie 信息

**接口路径**: `GET /api/cookie`

**功能描述**: 获取单个或所有 Cookie 信息

**请求参数**:
- **Query Parameters**:
  - `DedeUserID` (string, 可选): 用户ID，不提供则返回所有Cookie列表
- **Headers**:
  - `token` (string, 可选*): API Token（当提供DedeUserID时必填）

**成功响应（单个Cookie）**:
```json
{
  "cookie_info": {
    "cookies": [...]
  },
  "token_info": {...},
  "_cookiemgmt": {...},
  "cookie_valid": true,
  "refresh_status": "success",
  "check_time": "检查时间",
  "error_message": "错误信息"
}
```

**成功响应（Cookie列表）**:
```json
[
  {
    "DedeUserID": "用户ID",
    "update_time": 更新时间戳,
    "expire_time": 过期时间戳,
    "check_time": "检查时间",
    "cookie_valid": true,
    "refresh_status": "success",
    "enabled": true
  }
]
```

**错误响应**:
- `404`: 未找到指定的 Cookie 信息

### 3.2 随机获取有效 Cookie

**接口路径**: `GET /api/cookie/random`

**功能描述**: 从所有有效且启用的 Cookie 中随机选择一个返回

**请求参数**:
- **Query Parameters**:
  - `type` (string, 可选): 返回格式类型，可选值：`sim`（简化格式）
- **Headers**:
  - `token` (string, 可选*): API Token

**成功响应（默认格式）**:
```json
{
  "cookie_info": {
    "cookies": [...]
  },
  "token_info": {...},
  "_cookiemgmt": {...}
}
```

**成功响应（简化格式，type="sim"）**:
```json
{
  "code": 0,
  "message": "获取成功",
  "cookie": "DedeUserID=值;DedeUserID__ckMd5=值;SESSDATA=值;bili_jct=值;buvid3=值;buvid4=值;"
}
```

**错误响应**:
- `401`: 认证失败
- `404`: 无可用的有效 Cookie
- `500`: 生成Cookie字符串失败

### 3.3 检查 Cookie

**接口路径**: `GET /api/cookie/check`

**功能描述**: 检查指定用户的 Cookie 有效性

**请求参数**:
- **Query Parameters**:
  - `DedeUserID` (string, 必填): 用户ID
- **Headers**:
  - `token` (string, 可选*): API Token

**成功响应**:
```json
{
  "code": 0,
  "message": "Cookie 有效",
  "is_valid": true
}
```

**失败响应**:
```json
{
  "code": 错误码,
  "message": "错误信息",
  "is_valid": false
}
```

### 3.4 检查所有 Cookie

**接口路径**: `GET /api/cookie/check_all`

**功能描述**: 检查所有 Cookie 的有效性

**请求参数**:
- **Headers**:
  - `token` (string, 可选*): API Token

**成功响应**:
```json
{
  "code": 0,
  "message": "已检查所有Cookie"
}
```

### 3.5 测试 Cookie

**接口路径**: `POST /api/cookie/test`

**功能描述**: 测试提供的 Cookie 字符串有效性

**请求参数**:
- **Body**:
  ```json
  {
    "cookie": "cookie字符串"
  }
  ```
- **Headers**:
  - `token` (string, 可选*): API Token

**响应**: 返回 Cookie 有效性检查结果

**错误响应**:
- `400`: 缺少 cookie 参数
- `401`: 认证失败

### 3.6 刷新 Cookie

**接口路径**: `GET /api/cookie/refresh`

**功能描述**: 刷新指定用户的 Cookie

**请求参数**:
- **Query Parameters**:
  - `DedeUserID` (string, 必填): 用户ID
- **Headers**:
  - `token` (string, 可选*): API Token

**成功响应**:
```json
{
  "code": 0,
  "message": "刷新成功",
  "expire_time": 过期时间戳
}
```

**失败响应**:
```json
{
  "code": 错误码,
  "message": "错误信息"
}
```

### 3.7 刷新所有 Cookie

**接口路径**: `GET /api/cookie/refresh_all`

**功能描述**: 刷新所有过期的 Cookie

**请求参数**:
- **Headers**:
  - `token` (string, 可选*): API Token

**成功响应**:
```json
{
  "code": 0,
  "message": "已刷新所有Cookie"
}
```

### 3.8 删除 Cookie

**接口路径**: `DELETE /api/cookie/delete`

**功能描述**: 删除指定用户的 Cookie 文件

**请求参数**:
- **Query Parameters**:
  - `DedeUserID` (string, 必填): 用户ID
- **Headers**:
  - `token` (string, 可选*): API Token

**成功响应**:
```json
{
  "code": 0,
  "message": "删除成功"
}
```

**错误响应**:
- `404`: 指定的 Cookie 文件不存在
- `500`: 删除文件失败

### 3.9 切换 Cookie 启用状态

**接口路径**: `POST /api/cookie/toggle`

**功能描述**: 切换指定用户 Cookie 的启用/禁用状态

**请求参数**:
- **Body**:
  ```json
  {
    "DedeUserID": "用户ID"
  }
  ```
- **Headers**:
  - `token` (string, 可选*): API Token

**成功响应**:
```json
{
  "code": 0,
  "message": "切换成功",
  "enabled": true
}
```

**错误响应**:
- `404`: 指定的 Cookie 文件不存在
- `500`: 处理文件失败

---

## 错误码说明

| HTTP状态码 | 说明 |
|------------|------|
| 200 | 请求成功 |
| 400 | 请求参数错误 |
| 401 | 认证失败（缺失或无效的API Token） |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

## 注意事项

1. **API Token**: 标记为 `可选*` 的参数表示当服务器启用 API Token 验证时为必填
2. **文件格式**: 系统只处理包含 `_cookiemgmt` 字段的新格式 Cookie 文件
3. **实时性**: Cookie 相关操作会实时扫描文件系统，确保数据最新
4. **错误处理**: 文件解析错误不会中断整个流程，会记录日志并继续处理
5. **通知**: 删除操作会触发 Gotify 通知（如果配置）

## 使用示例

### 获取随机 Cookie（简化格式）
```bash
curl -X GET "http://localhost:8000/api/cookie/random?type=sim" \
  -H "token: your_api_token"
```

### 检查指定用户 Cookie
```bash
curl -X GET "http://localhost:8000/api/cookie/check?DedeUserID=123456" \
  -H "token: your_api_token"
```

### 切换 Cookie 启用状态
```bash
curl -X POST "http://localhost:8000/api/cookie/toggle" \
  -H "Content-Type: application/json" \
  -H "token: your_api_token" \
  -d '{"DedeUserID": "123456"}'
```