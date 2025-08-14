# BilibiliCookieMgmt API 文档

## 项目概述

BilibiliCookieMgmt 是一个基于 FastAPI 的 Bilibili Cookie 管理系统，提供完整的 Cookie 生命周期管理功能，包括扫码登录、健康检查、自动刷新、有效性验证等。

## 系统架构

### 核心模块
- **认证模块** (`core.auth`): 处理 Bilibili TV 签名和用户代理
- **Cookie 管理** (`core.cookie`): Cookie 存储、验证、刷新和健康检查
- **配置管理** (`core.config`): 统一配置管理系统
- **通知系统** (`core.notifications`): Gotify 消息推送
- **调度器** (`core.scheduler`): 定时任务管理
- **路由系统** (`core.routes`): API 端点定义

### 数据存储
- Cookie 数据以 JSON 格式存储在 `data/cookie/` 目录
- 每个用户一个文件，文件名为 `{DedeUserID}.json`

## API 基本信息

- **基础URL**: `http://{HOST}:{PORT}` (默认: `http://0.0.0.0:18000`)
- **认证方式**: HTTP Header `token` 字段
- **数据格式**: JSON
- **字符编码**: UTF-8

## 认证机制

### API Token 验证
大部分 API 接口需要通过 HTTP 请求头进行认证：

```http
token: YOUR_API_TOKEN
```

**认证配置**:
- 可通过 `config.yaml` 中的 `API_TOKEN.enable` 启用/禁用
- Token 值在 `API_TOKEN.token` 中配置
- 未启用时所有接口无需认证

**认证错误响应**:
```json
{
  "detail": "缺失 API Token"  // HTTP 401
}
```

```json
{
  "detail": "无效的 API Token"  // HTTP 401
}
```

## API 端点详细说明

### 1. 主页访问

**端点**: `GET /`

**描述**: 返回 Web 管理界面

**认证**: 不需要

**响应**: HTML 页面 (`static/index.html`)

---

### 2. 生成登录二维码

**端点**: `GET /api/passport-login/web/qrcode/generate`

**描述**: 生成 Bilibili 登录二维码

**认证**: 必需

**实现细节**:
- 调用 Bilibili TV 登录 API
- 使用 TV 签名算法进行请求签名
- 返回二维码认证码和登录 URL

**成功响应**:
```json
{
  "code": 0,
  "data": {
    "auth_code": "xxxxxxxxxxxxxxxx",
    "url": "https://passport.bilibili.com/qrcode/h5/login?auth_code=xxxxxxxx"
  }
}
```

**错误响应**:
```json
{
  "detail": "网络请求失败信息"  // HTTP 500
}
```

---

### 3. 轮询扫码状态

**端点**: `GET /api/passport-login/web/qrcode/poll`

**描述**: 轮询二维码扫码状态

**认证**: 必需

**查询参数**:
- `auth_code` (必需): 二维码生成接口返回的认证码

**实现细节**:
- 扫码成功后自动保存 Cookie 数据
- 自动获取和保存 buvid3/buvid4
- 自动执行 Cookie 有效性检查
- 发送登录成功通知

**扫码成功响应**:
```json
{
  "code": 0,
  "message": "扫码成功",
  "data": {
    "token_info": {
      "mid": 123456789,
      "access_token": "xxxxxxxx",
      "refresh_token": "xxxxxxxx",
      "expires_in": 2592000
    },
    "cookie_info": {
      "cookies": [
        {
          "name": "DedeUserID",
          "value": "123456789",
          "http_only": 0,
          "expires": 1234567890,
          "secure": 0
        }
        // ... 更多 cookie 项
      ],
      "domains": [".bilibili.com"]
    }
  }
}
```

**等待扫码响应**:
```json
{
  "code": 86090,
  "message": "等待扫码"
}
```

**二维码失效响应**:
```json
{
  "code": 86038,
  "message": "二维码已失效"
}
```

---

### 4. 获取 Cookie 信息

**端点**: `GET /api/cookie`

**描述**: 获取用户 Cookie 信息

**认证**: 必需

**查询参数**:
- `DedeUserID` (可选): 指定用户 ID，不提供则返回所有用户信息

**获取所有用户响应**:
```json
[
  {
    "DedeUserID": "123456789",
    "update_time": 1698765432123,
    "expire_time": 1698766432123,
    "check_time": 1698765432123,
    "cookie_valid": true,
    "refresh_status": "success",
    "username": "用户名"
  }
  // ... 更多用户
]
```

**获取指定用户响应**:
```json
{
  "token_info": {
    "mid": 123456789,
    "access_token": "xxxxxxxx",
    "refresh_token": "xxxxxxxx",
    "expires_in": 2592000
  },
  "cookie_info": {
    "cookies": [
      {
        "name": "DedeUserID",
        "value": "123456789",
        "http_only": 0,
        "expires": 1234567890,
        "secure": 0
      }
      // ... 更多 cookie 项
    ],
    "domains": [".bilibili.com"]
  },
  "_cookiemgmt": {
    "update_time": 1698765432123,
    "username": "用户名",
    "cookie_valid": true,
    "last_check_time": 1698765432123,
    "last_refresh_time": 1698765432123,
    "refresh_status": "success",
    "error_message": null,
    "enabled": true
  },
  "check_time": 1698765432123,
  "cookie_valid": true,
  "refresh_status": "success"
}
```

**错误响应**:
```json
{
  "detail": "未找到指定的 Cookie 信息"  // HTTP 404
}
```

---

### 5. 随机获取有效 Cookie

**端点**: `GET /api/cookie/random`

**描述**: 随机返回一个有效的 Cookie

**认证**: 必需

**查询参数**:
- `type` (可选): 值为 `sim` 时返回简化的 Cookie 字符串格式

**实现细节**:
- 只返回 `cookie_valid: true` 且 `enabled: true` 的 Cookie
- 自动过滤无效和禁用的 Cookie
- 支持简化格式输出

**标准格式响应**:
```json
{
  "token_info": { /* ... */ },
  "cookie_info": { /* ... */ },
  "_cookiemgmt": { /* ... */ }
}
```

**简化格式响应** (`type=sim`):
```json
{
  "code": 0,
  "message": "获取成功",
  "cookie": "DedeUserID=123456789;DedeUserID__ckMd5=abcd1234;SESSDATA=xxxx;bili_jct=yyyy;buvid3=xxxx;buvid4=yyyy;"
}
```

**错误响应**:
```json
{
  "detail": "无可用的有效 Cookie"  // HTTP 404
}
```

---

### 6. 检查 Cookie 有效性

**端点**: `GET /api/cookie/check`

**描述**: 检查指定用户的 Cookie 有效性

**认证**: 必需

**查询参数**:
- `DedeUserID` (必需): 要检查的用户 ID

**实现细节**:
- 调用 Bilibili API 验证 Cookie
- 自动更新 buvid3/buvid4 (如缺失)
- 更新检查时间和有效性状态
- 无效时发送 Gotify 通知

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
  "code": -2,
  "message": "Cookie 无效",
  "is_valid": false
}
```

---

### 7. 检查所有 Cookie

**端点**: `GET /api/cookie/check_all`

**描述**: 检查所有用户的 Cookie 有效性

**认证**: 必需

**实现细节**:
- 并发检查所有 Cookie 文件
- 自动处理空文件和无效文件
- 发送异常文件通知

**响应**:
```json
{
  "code": 0,
  "message": "已检查所有Cookie"
}
```

---

### 8. 测试 Cookie 字符串

**端点**: `POST /api/cookie/test`

**描述**: 测试提供的 Cookie 字符串有效性

**认证**: 必需

**请求体**:
```json
{
  "cookie": "DedeUserID=123456789;SESSDATA=xxxx;bili_jct=yyyy;"
}
```

**成功响应**:
```json
{
  "code": 0,
  "message": "Cookie 有效"
}
```

**失败响应**:
```json
{
  "code": -2,
  "message": "Cookie 无效"
}
```

**错误响应**:
```json
{
  "detail": "缺少 cookie 参数"  // HTTP 400
}
```

---

### 9. 刷新 Cookie

**端点**: `GET /api/cookie/refresh`

**描述**: 刷新指定用户的 Cookie

**认证**: 必需

**查询参数**:
- `DedeUserID` (必需): 要刷新的用户 ID

**实现细节**:
- 使用 refresh_token 刷新 access_token
- 自动获取新的 Cookie 信息
- 更新 buvid3/buvid4
- 发送刷新成功通知

**成功响应**:
```json
{
  "code": 0,
  "message": "刷新成功",
  "expire_time": 1698766432123
}
```

**失败响应**:
```json
{
  "code": -1,
  "message": "刷新失败: 具体错误信息"
}
```

---

### 10. 刷新所有 Cookie

**端点**: `GET /api/cookie/refresh_all`

**描述**: 刷新所有需要刷新的 Cookie

**认证**: 必需

**实现细节**:
- 检查所有 Cookie 的更新时间
- 只刷新超过刷新间隔的 Cookie
- 自动处理旧格式 Cookie 文件

**响应**:
```json
{
  "code": 0,
  "message": "已刷新所有Cookie"
}
```

---

### 11. 删除 Cookie

**端点**: `DELETE /api/cookie/delete`

**描述**: 删除指定用户的 Cookie 文件

**认证**: 必需

**查询参数**:
- `DedeUserID` (必需): 要删除的用户 ID

**实现细节**:
- 物理删除 Cookie 文件
- 发送删除通知

**成功响应**:
```json
{
  "code": 0,
  "message": "删除成功"
}
```

**错误响应**:
```json
{
  "detail": "指定的 Cookie 文件不存在"  // HTTP 404
}
```

```json
{
  "detail": "删除文件失败: 具体错误信息"  // HTTP 500
}
```

## 数据结构说明

### Cookie 文件结构

每个用户的 Cookie 数据以 JSON 格式存储，包含以下字段：

```json
{
  "token_info": {
    "mid": 123456789,
    "access_token": "访问令牌",
    "refresh_token": "刷新令牌",
    "expires_in": 2592000
  },
  "cookie_info": {
    "cookies": [
      {
        "name": "cookie名称",
        "value": "cookie值",
        "http_only": 0,
        "expires": 1234567890,
        "secure": 0
      }
    ],
    "domains": [".bilibili.com"]
  },
  "_cookiemgmt": {
    "update_time": 1698765432123,
    "username": "用户名",
    "cookie_valid": true,
    "last_check_time": 1698765432123,
    "last_refresh_time": 1698765432123,
    "refresh_status": "success",
    "error_message": null,
    "enabled": true
  }
}
```

### 管理字段说明 (`_cookiemgmt`)

- `update_time`: Cookie 最后更新时间 (毫秒时间戳)
- `username`: 用户名 (从 DedeUserID__ckMd5 提取)
- `cookie_valid`: Cookie 有效性状态
- `last_check_time`: 最后检查时间
- `last_refresh_time`: 最后刷新时间
- `refresh_status`: 刷新状态 (`success`, `failed`, `unknown`)
- `error_message`: 错误信息 (有效时为 null)
- `enabled`: 是否启用 (默认 true)

## 自动化功能

### 定时健康检查

**配置项**: `COOKIE_CHECK`
- `enable`: 是否启用定时检查
- `check_intlval`: 检查间隔 (秒，默认 600)

**功能**:
- 定时检查所有 Cookie 有效性
- 自动更新检查状态
- 发送失效通知

### 定时自动刷新

**配置项**: `COOKIE_REFRESH`
- `enable`: 是否启用自动刷新
- `refresh_intlval`: 刷新间隔 (天，默认 30)

**功能**:
- 每日检查需要刷新的 Cookie
- 自动刷新即将过期的 Cookie
- 发送刷新结果通知

### 通知系统

**Gotify 配置**: `PUSH.GOTIFY`
- `enable`: 是否启用 Gotify 通知
- `url`: Gotify 服务器地址
- `token`: Gotify 应用 Token

**通知事件**:
- Cookie 失效
- Cookie 刷新成功/失败
- Cookie 删除
- 文件异常 (空文件、无效文件)
- 用户登录成功

## 错误处理

### HTTP 状态码

- `200`: 请求成功
- `400`: 请求参数错误
- `401`: 认证失败
- `404`: 资源不存在
- `500`: 服务器内部错误

### 业务错误码

- `0`: 成功
- `-1`: 一般错误
- `-2`: Cookie 无效
- `86038`: 二维码已失效
- `86090`: 等待扫码中

### 错误响应格式

**FastAPI 标准错误**:
```json
{
  "detail": "错误描述信息"
}
```

**业务逻辑错误**:
```json
{
  "code": -1,
  "message": "具体错误信息"
}
```

## 安全考虑

### API Token 保护
- 支持启用/禁用 API Token 验证
- Token 通过 HTTP Header 传递
- 建议在生产环境启用 HTTPS

### Cookie 数据保护
- Cookie 数据本地文件存储
- 敏感信息不记录到日志
- 支持禁用特定用户的 Cookie

### 网络安全
- 使用官方 User-Agent
- 请求签名验证
- 超时控制和重试机制

## 配置文件说明

完整的配置文件示例 (`config.yaml`):

```yaml
# 服务器配置
HOST: 0.0.0.0
PORT: 18000

# API Token 配置
API_TOKEN:
  enable: true
  token: "your_api_token_here"

# Cookie 存储配置
COOKIE_FOLDER: "data/cookie"

# 健康检查配置
COOKIE_CHECK:
  enable: true
  check_intlval: 600  # 10分钟

# 自动刷新配置
COOKIE_REFRESH:
  enable: true
  refresh_intlval: 30  # 30天

# 通知配置
PUSH:
  GOTIFY:
    enable: true
    url: "http://your-gotify-server:port"
    token: "your_gotify_token"
  EMAIL:
    enable: false  # 暂未实现
```

## 使用示例

### Python 客户端示例

```python
import requests

class BilibiliCookieClient:
    def __init__(self, base_url, api_token):
        self.base_url = base_url
        self.headers = {'token': api_token}
    
    def get_random_cookie(self, simple=False):
        """获取随机有效Cookie"""
        params = {'type': 'sim'} if simple else {}
        response = requests.get(
            f"{self.base_url}/api/cookie/random",
            headers=self.headers,
            params=params
        )
        return response.json()
    
    def check_cookie(self, dede_user_id):
        """检查Cookie有效性"""
        response = requests.get(
            f"{self.base_url}/api/cookie/check",
            headers=self.headers,
            params={'DedeUserID': dede_user_id}
        )
        return response.json()
    
    def test_cookie(self, cookie_string):
        """测试Cookie字符串"""
        response = requests.post(
            f"{self.base_url}/api/cookie/test",
            headers=self.headers,
            json={'cookie': cookie_string}
        )
        return response.json()

# 使用示例
client = BilibiliCookieClient('http://localhost:18000', 'your_token')

# 获取简化格式Cookie
cookie_data = client.get_random_cookie(simple=True)
print(cookie_data['cookie'])

# 检查Cookie有效性
result = client.check_cookie('123456789')
print(f"Cookie有效: {result['is_valid']}")
```

### JavaScript 客户端示例

```javascript
class BilibiliCookieAPI {
    constructor(baseURL, apiToken) {
        this.baseURL = baseURL;
        this.headers = { 'token': apiToken };
    }

    async getRandomCookie(simple = false) {
        const params = simple ? '?type=sim' : '';
        const response = await fetch(`${this.baseURL}/api/cookie/random${params}`, {
            headers: this.headers
        });
        return await response.json();
    }

    async checkAllCookies() {
        const response = await fetch(`${this.baseURL}/api/cookie/check_all`, {
            headers: this.headers
        });
        return await response.json();
    }

    async refreshCookie(dedeUserID) {
        const response = await fetch(`${this.baseURL}/api/cookie/refresh?DedeUserID=${dedeUserID}`, {
            headers: this.headers
        });
        return await response.json();
    }
}

// 使用示例
const api = new BilibiliCookieAPI('http://localhost:18000', 'your_token');

// 获取随机Cookie
api.getRandomCookie(true).then(data => {
    console.log('Cookie:', data.cookie);
});

// 检查所有Cookie
api.checkAllCookies().then(result => {
    console.log('检查完成:', result.message);
});
```

## 更新日志

### 当前版本特性

- ✅ 完整的 Cookie 生命周期管理
- ✅ Web 界面管理
- ✅ 自动健康检查和刷新
- ✅ Gotify 通知支持
- ✅ buvid3/buvid4 自动管理
- ✅ 并发处理和错误恢复
- ✅ 配置文件热加载

### 计划中的功能

- 📧 邮件通知支持
- 🔗 Webhook 通知支持
- 📊 使用统计和监控
- 🔐 更多认证方式
- 🌐 多语言支持

---

**项目地址**: [GitHub Repository]
**技术支持**: 如有问题请提交 Issue
**许可证**: [License Type]
