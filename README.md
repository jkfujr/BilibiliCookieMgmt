# Bilibili Cookie Management

一个基于 Python 和 Vuetify 的 比例比例 Cookie 管理工具。

![截图](https://github.com/user-attachments/assets/c61d0169-0d78-4387-8714-eeea9b56c5ac)

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

### 二进制运行 (推荐)

从 [发行版](https://github.com/jkfujr/BilibiliCookieMgmt/releases) 下载对应系统的最新构建。

1. 解压下载的压缩包。
2. 运行可执行文件，首次启动会在程序目录下自动生成 `data/config.json`、`data/data.db`、`data/data.key`，并在控制台输出初始 API Token。
   - 若仍存在旧版根目录 `config.yaml`，首次启动会自动迁移到 `data/config.json`。
   - Windows: 双击 `BilibiliCookieMgmt-CLI-win-x64.exe`
   - Linux/macOS:
     ```bash
     chmod +x BilibiliCookieMgmt-CLI-*
     ./BilibiliCookieMgmt-CLI-*
     ```
   - 支持通过命令行参数指定配置文件路径：
     ```bash
     ./BilibiliCookieMgmt-CLI-* -c /path/to/custom_config.json
     ```

### Docker

1. 拉取最新镜像：

```bash
docker pull ghcr.io/jkfujr/bilibilicookiemgmt:latest
```

2. 启动服务。首次启动会在容器 `/app/data/config.json` 生成配置；挂载 `./data:/app/data` 后会写入宿主机的 `./data/config.json`，并在容器日志中输出初始 API Token。

```bash
docker run -d --name bilibili-cookie-mgmt \
  -p 18000:18000 \
  -v ./data:/app/data \
  ghcr.io/jkfujr/bilibilicookiemgmt:latest
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
pip install fastapi uvicorn pyyaml httpx aiofiles aiosqlite cryptography
python main.py
```

源码运行时，默认配置固定在后端目录 `BilibiliCookieMgmt/data/config.json`，不会随启动命令所在目录变化。

## 访问

浏览器访问：`http://127.0.0.1:18000`

# 联系方式

Rec-NIC 今天也是咕咕咕的一天 108737089

    (录播姬非官方闲聊群但是官方)

# 致谢
> 该仓库的登录及刷新功能主要参考了 @cibimo 的 bilibiliLogin 项目, 感谢!
> 
> bilibiliLogin https://github.com/cibimo/bilibiliLogin
