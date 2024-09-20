import asyncio
import httpx
import logging

"""
Gotify模块

提供Gotify异步消息推送功能。可以直接传入IP、token、标题、消息和优先级等参数。

函数：
    push_gotify(ip, token, title, message, priority=1, max_retries=3, retry_delay=3)
        异步推送消息到Gotify。
        参数：
            ip: Gotify服务器的IP地址（可以包含协议）。
            token: Gotify服务器的token。
            title: 消息标题。
            message: 消息内容。
            priority: 消息优先级，默认值为1。
            max_retries: 最大重试次数，默认值为3。
            retry_delay: 重试间隔时间（秒），默认值为3。
"""

# 禁用请求日志
httpx_loggers = ["httpx", "httpx.client", "httpx._client", "httpx._transports"]
for logger_name in httpx_loggers:
    logging.getLogger(logger_name).propagate = False
    logging.getLogger(logger_name).disabled = True

async def push_gotify(ip, token, title, message, priority=1, max_retries=3, retry_delay=3):
    if not ip.startswith("http://") and not ip.startswith("https://"):
        ip = f"https://{ip}"

    url = f"{ip}/message?token={token}"
    payload = {
        "message": message,
        "priority": priority,
        "title": title
    }

    async with httpx.AsyncClient(verify=False) as client:
        for attempt in range(1, max_retries + 1):
            try:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    logging.info("[Gotify] 信息推送成功")
                    break
                else:
                    logging.error(f"[Gotify] 信息推送失败，状态码：{resp.status_code}，重试次数：{attempt}/{max_retries}")
            except Exception as e:
                logging.error(f"[Gotify] 信息推送异常：{e}，重试次数：{attempt}/{max_retries}")
            await asyncio.sleep(retry_delay)
        else:
            logging.error(f"[Gotify] 信息推送失败：达到最大重试次数 {max_retries} 次")
