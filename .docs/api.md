# API 文档

本项目提供了一套 RESTful API，用于管理 Bilibili Cookie，包括扫码登录、Cookie 的增删改查、以及有效性检查与刷新。

## 基础信息

- **Base URL**: `/api/v1`
- **鉴权方式**: Bearer Token
  - 当配置中启用 API Token (`api_token.enable = true`) 时，需要在请求头中携带 `Authorization: Bearer <your_token>`。
  - 若未启用鉴权，则无需携带。

## 1. 系统接口

### 健康检查
用于检查服务是否正常运行。

- **Endpoint**: `GET /health`
- **Auth**: 无需鉴权
- **Response**:
  ```json
  {
    "status": "ok"
  }
  ```

---

## 2. 扫码登录 (Auth)

提供 Bilibili TV 端扫码登录功能。

### 2.1 获取登录二维码
生成用于扫码登录的二维码信息。

- **Endpoint**: `GET /auth/tv/qrcode`
- **Response**:
  ```json
  {
    "auth_code": "xxxxx",       // 用于后续轮询的凭证
    "qrcode_url": "https://..." // 二维码链接
  }
  ```

### 2.2 轮询登录状态
检查用户是否已扫码并确认登录。

- **Endpoint**: `GET /auth/tv/poll`
- **Query Parameters**:
  - `auth_code` (required): `GET /auth/tv/qrcode` 接口返回的 `auth_code`
- **Response**:
  - **登录成功**: 返回保存后的 Cookie 文档（包含管理信息）。
  - **等待扫码/未确认**:
    ```json
    {
      "code": 86039,
      "message": "未确认"
    }
    ```
  - **二维码过期**:
    ```json
    {
      "code": 86038,
      "message": "二维码已过期"
    }
    ```

---

## 3. Cookie 管理 (Cookies)

### 3.1 获取随机 Cookie
获取一个可用的 Cookie，常用于爬虫轮询。

- **Endpoint**: `GET /cookies/random`
- **Query Parameters**:
  - `format`: 返回格式，默认为 `simple`。
    - `simple`: 仅返回 Cookie 字符串 (Header String)。
    - `json`: 返回完整的 Cookie 管理对象。
- **Response**:
  - `format=simple`:
    ```text
    SESSDATA=...; bili_jct=...; DedeUserID=...;
    ```
  - `format=json`: (见下方 Cookie 对象结构)

### 3.2 获取所有 Cookie
返回系统中存储的所有 Cookie 列表。

- **Endpoint**: `GET /cookies/`
- **Response**: List[CookieObject]

### 3.3 获取指定 Cookie
根据 DedeUserID 获取单个 Cookie 信息。

- **Endpoint**: `GET /cookies/{DedeUserID}`
- **Path Parameters**:
  - `DedeUserID`: Bilibili 用户 ID
- **Response**: CookieObject

### 3.4 删除 Cookie
删除指定的 Cookie。

- **Endpoint**: `DELETE /cookies/{DedeUserID}`
- **Response**:
  ```json
  {
    "deleted": true,
    "DedeUserID": "123456"
  }
  ```

### 3.5 测试 Cookie 有效性
测试给定的 Cookie 字符串是否有效（不保存）。

- **Endpoint**: `POST /cookies/test`
- **Body**:
  ```json
  {
    "cookie": "SESSDATA=...; bili_jct=...;"
  }
  ```
- **Response**:
  ```json
  {
    "valid": true,
    "message": "有效 (用户: xxx)",
    "uid": "123456"
  }
  ```

### 3.6 批量检查 Cookie
触发对已存储 Cookie 的有效性检查。

- **Endpoint**: `POST /cookies/check`
- **Query Parameters**:
  - `all`: `true` 表示检查所有 Cookie。
- **Body** (Optional):
  ```json
  {
    "ids": ["123456", "234567"] // 指定要检查的 ID 列表
  }
  ```
- **Response**: 返回检查结果摘要。

### 3.7 批量刷新 Cookie
触发对已存储 Cookie 的刷新操作（针对即将过期的 Cookie）。

- **Endpoint**: `POST /cookies/refresh`
- **Query Parameters**:
  - `all`: `true` 表示刷新所有 Cookie。
- **Body** (Optional):
  ```json
  {
    "ids": ["123456"] // 指定要刷新的 ID 列表
  }
  ```
- **Response**: 返回刷新结果摘要。

### 3.8 启用/禁用 Cookie
设置 Cookie 的启用状态。禁用的 Cookie 不会被 `random` 接口返回，但仍会参与检查和刷新。

- **Endpoint**: `PATCH /cookies/{DedeUserID}/enabled`
- **Body**:
  ```json
  {
    "is_enabled": false
  }
  ```
- **Response**: 更新后的 CookieObject

---

## 数据模型

### CookieObject (Cookie 文档)
存储在数据库中的完整结构。

```json
{
  "raw": { ... }, // 原始 Bilibili 登录响应数据
  "managed": {
    "DedeUserID": "123456",
    "username": "bili_user",
    "status": "valid",           // valid, invalid, expired, unknown
    "is_enabled": true,          // 是否启用
    "header_string": "...",      // 拼接好的 Cookie 字符串
    "update_time": "2023-10-01T12:00:00",
    "last_check_time": "2023-10-01T12:00:00",
    "last_refresh_time": "2023-10-01T12:00:00",
    "refresh_status": "not_needed", // success, failed, pending, not_needed
    "error_message": null
  }
}
```
