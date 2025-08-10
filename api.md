# API文档

## 基本信息

- 基础URL: 由配置文件决定，默认为 `http://[HOST]:[PORT]`
- 认证方式: 通过请求头 `token` 字段进行认证
- 数据格式: 所有响应均为JSON格式

## 认证

大部分API接口需要通过HTTP请求头中的 `token`字段进行认证：

```
token: 你的API_TOKEN
```

API_TOKEN在配置文件中设置，如果启用了 `API_TOKEN`功能。

## API

### 1. 主页

**请求**:

- 路径: `/`
- 方法: `GET`
- 认证: 不需要

**响应**:

- 返回静态HTML页面

### 2. 生成二维码

**请求**:

- 路径: `/api/passport-login/web/qrcode/generate`
- 方法: `GET`
- 认证: 必需

**响应**:

```json
{
  "code": 0,
  "data": {
    "auth_code": "xxxxxxxxxxxxxxxx",
    "url": "https://passport.bilibili.com/qrcode/h5/login?auth_code=xxxxxxxx"
  }
}
```

### 3. 轮询扫码状态

**请求**:

- 路径: `/api/passport-login/web/qrcode/poll`
- 方法: `GET`
- 参数:
  - `auth_code`: 二维码生成接口返回的auth_code
- 认证: 必需

**响应**:

- 扫码成功:

```json
{
  "code": 0,
  "message": "扫码成功",
  "data": {
    "token_info": { ... },
    "cookie_info": { ... }
  }
}
```

- 二维码失效:

```json
{
  "code": 86038,
  "message": "二维码已失效"
}
```

- 等待扫码:

```json
{
  "code": 86090,
  "message": "等待扫码"
}
```

### 4. 获取Cookie信息

**请求**:

- 路径: `/api/cookie`
- 方法: `GET`
- 参数:
  - `DedeUserID`: (可选) 指定用户ID，不提供则返回所有用户信息
- 认证: 必需

**响应**:

- 获取所有用户:

```json
[
  {
    "DedeUserID": "12345678",
    "update_time": 1698765432123,
    "expire_time": 1698766432123,
    "check_time": 1698765432123,
    "cookie_valid": true
  },
  ...
]
```

- 获取指定用户:

```json
{
  "update_time": 1698765432123,
  "token_info": { ... },
  "cookie_info": { ... },
  "check_time": 1698765432123,
  "cookie_valid": true
}
```

### 5. 随机获取有效Cookie

**请求**:

- 路径: `/api/cookie/random`
- 方法: `GET`
- 参数:
  - `type`: (可选) 如果值为 `sim`，则返回简化版Cookie字符串
- 认证: 必需

**响应**:

- 标准响应:

```json
{
  "update_time": 1698765432123,
  "token_info": { ... },
  "cookie_info": { ... },
  "check_time": 1698765432123,
  "cookie_valid": true
}
```

- 简化版响应 (type=sim):

```json
{
  "code": 0,
  "message": "获取成功",
  "cookie": "DedeUserID=12345678;DedeUserID__ckMd5=abcd1234;SESSDATA=xxxx;bili_jct=yyyy;"
}
```

### 6. 检查Cookie有效性

**请求**:

- 路径: `/api/cookie/check`
- 方法: `GET`
- 参数:
  - `DedeUserID`: 要检查的用户ID
- 认证: 必需

**响应**:

```json
{
  "code": 0,
  "message": "Cookie 有效",
  "is_valid": true
}
```

### 7. 检查所有Cookie

**请求**:

- 路径: `/api/cookie/check_all`
- 方法: `GET`
- 认证: 必需

**响应**:

```json
{
  "code": 0,
  "message": "已检查所有Cookie"
}
```

### 8. 测试Cookie

**请求**:

- 路径: `/api/cookie/test`
- 方法: `POST`
- 请求体:

```json
{
  "cookie": "DedeUserID=12345678;DedeUserID__ckMd5=abcd1234;SESSDATA=xxxx;bili_jct=yyyy;"
}
```

- 认证: 必需

**响应**:

```json
{
  "code": 0,
  "message": "Cookie 有效"
}
```

### 9. 刷新Cookie

**请求**:

- 路径: `/api/cookie/refresh`
- 方法: `GET`
- 参数:
  - `DedeUserID`: 要刷新的用户ID
- 认证: 必需

**响应**:

```json
{
  "code": 0,
  "message": "刷新成功",
  "expire_time": 1698766432123
}
```

### 10. 刷新所有Cookie

**请求**:

- 路径: `/api/cookie/refresh_all`
- 方法: `GET`
- 认证: 必需

**响应**:

```json
{
  "code": 0,
  "message": "已刷新所有Cookie"
}
```

### 11. 删除Cookie

**请求**:

- 路径: `/api/cookie/delete`
- 方法: `DELETE`
- 参数:
  - `DedeUserID`: 要删除的用户ID
- 认证: 必需

**响应**:

```json
{
  "code": 0,
  "message": "删除成功"
}
```

## 错误响应

当API调用失败时，会返回以下格式的错误响应：

```json
{
  "code": -1,
  "message": "错误信息"
}
```

常见错误码：

- `-1`: 一般错误
- `-2`: Cookie无效
- `86038`: 二维码已失效
- `86090`: 等待扫码中

HTTP状态码：

- `400`: 请求参数错误
- `401`: 未认证或认证失败
- `404`: 资源不存在
- `500`: 服务器内部错误
