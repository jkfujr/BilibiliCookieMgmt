# Bilibili Cookie Management

一个基于 Python 和 Vuetify 的 比例比例 Cookie 管理工具。

![截图](https://github.com/user-attachments/assets/a2f4895a-2588-42cc-a0c0-cc9f801ca563)

## 功能特性

- **Web 管理界面**：
  - 扫码登录/添加账号
  - 账号状态（有效/过期/失效统计）
- **自动化任务**：
  - 定时 Cookie 健康检查
  - 定时自动刷新 (自动续期)
- **消息推送**：
  - Gotify 通知支持

## 快速开始

### Docker Compose (推荐)

1. 确保根目录存在 `config.yaml` 配置文件。
2. 启动服务：

```bash
docker-compose up -d --build
```

### 源码运行

**1. 前端构建**

```bash
cd BilibiliCookieMgmt-web
npm install
npm run build
# 构建完成后，需将 dist 目录下的所有文件复制到后端 static 目录
# cp -r dist/* ../BilibiliCookieMgmt/static/
```

**2. 后端运行** (Python 3.11+)

```bash
cd BilibiliCookieMgmt
pip install fastapi uvicorn pyyaml httpx aiofiles
python main.py
```

## 访问

浏览器访问：`http://127.0.0.1:18000`

# 联系方式

Rec-NIC 今天也是咕咕咕的一天 108737089

    (录播姬非官方闲聊群但是官方)

# 致谢
> 该仓库的登录及刷新功能主要参考了 @cibimo 的 bilibiliLogin 项目, 感谢!
> 
> bilibiliLogin https://github.com/cibimo/bilibiliLogin
