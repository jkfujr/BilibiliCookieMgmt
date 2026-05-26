from __future__ import annotations

"""
只探测 bili_ticket 接口返回结构。

用法示例:
  $env:BILI_COOKIE = "SESSDATA=...; bili_jct=..."
  python BilibiliCookieMgmt/scripts/probe_bili_ticket.py

脚本只请求 GenWebTicket，不刷新 Cookie，不写入本地仓储。
默认隐藏 ticket 完整值，只输出有效期相关字段。
"""

import argparse
import asyncio
import getpass
import hashlib
import hmac
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import httpx


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0.7103.48 Safari/537.36"
)
TICKET_URL = "https://api.bilibili.com/bapis/bilibili.api.ticket.v1.Ticket/GenWebTicket"
TICKET_KEY = "XgwSnGZ1p"


def parse_cookie_header(header: str) -> Dict[str, str]:
    cookies: Dict[str, str] = {}
    for part in str(header or "").split(";"):
        item = part.strip()
        if not item or "=" not in item:
            continue
        name, value = item.split("=", 1)
        cookies[name.strip()] = value.strip()
    return cookies


def read_cookie(args: argparse.Namespace) -> str:
    if args.cookie_file:
        return Path(args.cookie_file).read_text(encoding="utf-8").strip()

    env_value = os.environ.get(args.cookie_env, "").strip()
    if env_value:
        return env_value

    if not sys.stdin.isatty():
        stdin_value = sys.stdin.read().strip()
        if stdin_value:
            return stdin_value

    return getpass.getpass("请输入 Cookie（输入不会回显）: ").strip()


def build_ticket_params(csrf: str) -> Dict[str, str]:
    ts = str(int(time.time()))
    message = f"ts{ts}"
    hexsign = hmac.new(TICKET_KEY.encode(), message.encode(), hashlib.sha256).hexdigest()
    return {
        "key_id": "ec02",
        "hexsign": hexsign,
        "context[ts]": ts,
        "csrf": csrf,
    }


def to_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def mask_ticket(ticket: str) -> str:
    if len(ticket) <= 12:
        return "***"
    return f"{ticket[:6]}...{ticket[-6:]}"


def summarize_response(status_code: int, data: Dict[str, Any], show_ticket: bool) -> Dict[str, Any]:
    inner = data.get("data", {}) if isinstance(data.get("data"), dict) else {}
    ticket = str(inner.get("ticket") or "")
    created_at = to_int(inner.get("created_at"))
    ttl = to_int(inner.get("ttl"))
    expires = created_at + ttl if created_at and ttl and ttl > 0 else None

    result: Dict[str, Any] = {
        "http_status": status_code,
        "code": data.get("code"),
        "message": data.get("message"),
        "ticket_present": bool(ticket),
        "created_at": created_at,
        "ttl": ttl,
        "expires": expires,
        "created_at_local": datetime.fromtimestamp(created_at).isoformat() if created_at else None,
        "expires_local": datetime.fromtimestamp(expires).isoformat() if expires else None,
        "raw_data_keys": sorted(inner.keys()),
    }
    if ticket:
        result["ticket"] = ticket if show_ticket else mask_ticket(ticket)
    return result


async def probe(cookie_header: str, show_ticket: bool) -> Dict[str, Any]:
    cookie_map = parse_cookie_header(cookie_header)
    csrf = cookie_map.get("bili_jct", "")
    if not csrf:
        raise ValueError("Cookie 中缺少 bili_jct，无法请求 bili_ticket")

    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://www.bilibili.com/",
        "Cookie": cookie_header,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(TICKET_URL, params=build_ticket_params(csrf), headers=headers)
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"接口未返回 JSON: HTTP {response.status_code}") from exc

    return summarize_response(response.status_code, data, show_ticket)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="探测 bili_ticket 接口是否返回有效期字段")
    parser.add_argument("--cookie-env", default="BILI_COOKIE", help="读取 Cookie 的环境变量名，默认 BILI_COOKIE")
    parser.add_argument("--cookie-file", help="从文件读取 Cookie，避免在命令行暴露")
    parser.add_argument("--show-ticket", action="store_true", help="显示完整 ticket，默认只显示脱敏值")
    return parser


async def main() -> int:
    args = build_parser().parse_args()
    cookie_header = read_cookie(args)
    summary = await probe(cookie_header, args.show_ticket)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("code") == 0 and summary.get("expires") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
