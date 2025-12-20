# 简介

![截图_2024-12-08_02-29-19](https://github.com/user-attachments/assets/a2f4895a-2588-42cc-a0c0-cc9f801ca563)

一个 python 实现的 BILIBILI COOKIE 管理器

## 功能

- 简单的web管理
- 消息推送
  - Gotify
- COOKIE
  - 扫码登录
  - 定时健康检查
  - 定时刷新 (默认到期一个月前)
  - API

# 说明

**_需要 Python 3.11 及以上版本_**

## 源码运行

### 1. 安装依赖

```bash
pip install -U fastapi uvicorn pyyaml httpx aiofiles
```

### 2. 准备配置与数据目录

- 配置文件：`./config.yaml`
- 数据目录：`./data`（默认 Cookie 存在 `./data/cookie`）

### 3. 启动

```bash
python main.py
```

### 4. 访问

- 首页：`http://127.0.0.1:18000/`
- 健康检查：`http://127.0.0.1:18000/api/v1/health`

## Docker

### 使用 docker

```bash
docker compose up -d --build
```

默认挂载：

- `./config.yaml:/app/config.yaml:ro`
- `./data:/app/data`

### 使用发布镜像

```bash
docker pull ghcr.io/jkfujr/bilibilicookiemgmt:latest
docker run -d \
  --name bilibili-cookie-mgmt \
  -p 18000:18000 \
  -v "$(pwd)/config.yaml:/app/config.yaml:ro" \
  -v "$(pwd)/data:/app/data" \
  ghcr.io/jkfujr/bilibilicookiemgmt:latest
```

# TODO

- 消息推送
  - WEBHOOK
  - EMAIL

# 联系方式

Rec-NIC 今天也是咕咕咕的一天 108737089

    (录播姬非官方闲聊群但是官方)

# 致谢
> 该仓库的登录及刷新功能主要参考了 @cibimo 的 bilibiliLogin 项目, 感谢!
> 
> bilibiliLogin https://github.com/cibimo/bilibiliLogin
