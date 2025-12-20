"""
迁移脚本: 将 v1 的 Cookie JSON(包含 _cookiemgmt)迁移为 v2 的两段式格式: 
{
  "raw": { 原始 v1 JSON },
  "managed": { 由仓库规则生成的管理信息 }
}

使用示例: 
  python scripts/migrate_v1_to_v2.py \
      --src ./v1/data/cookie \
      --dst auto \
      --ids 3298631 \
      --dry-run false \
      --overwrite true

注意: 
- 默认 src=./v1/data/cookie, dst=从 v2 配置读取(./data/cookie)。
- 如需写到 v2/data/cookie, 可显式指定 --dst ./v2/data/cookie。
"""

from __future__ import annotations

import os
import sys
import json
import asyncio
import argparse
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime


def _project_root_from_this_file() -> Path:
    # 本脚本位于 v2/scripts 下
    # 返回 v2 根目录
    return Path(__file__).resolve().parents[1]


def _ensure_v2_importable():
    """确保可以将 v2 作为包导入 (将项目根目录加入 sys.path)"""
    v2_root = _project_root_from_this_file()
    project_root = v2_root.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))



def _safe_load_json(file_path: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] 解析 JSON 失败: {file_path} -> {e}")
        return None


def _find_v1_files(src_dir: Path, ids: Optional[List[str]] = None) -> List[Path]:
    files: List[Path] = []
    if not src_dir.exists() or not src_dir.is_dir():
        print(f"[WARN] 源目录不存在或不是目录: {src_dir}")
        return files
    for p in src_dir.glob("*.json"):
        if ids:
            try:
                uid = p.stem
                if uid in ids:
                    files.append(p)
            except Exception:
                pass
        else:
            files.append(p)
    return files


def _extract_cookie_map(raw: Dict[str, Any]) -> Dict[str, str]:
    cookies = raw.get("cookie_info", {}).get("cookies", [])
    result: Dict[str, str] = {}
    for c in cookies:
        if isinstance(c, dict):
            name = c.get("name")
            val = c.get("value")
            if name is not None:
                result[str(name)] = str(val or "")
    return result


def _extract_dede_user_id(raw: Dict[str, Any]) -> Optional[str]:
    m = _extract_cookie_map(raw)
    v = m.get("DedeUserID")
    return str(v) if v is not None else None


async def _save_with_repo(raw: Dict[str, Any], dst_dir: Path) -> Tuple[bool, Optional[str], Optional[Path], Optional[str]]:
    """
    使用 v2 仓库保存为两段式文档。
    返回: (ok, dede_user_id, target_path, error)
    """
    # 确保 v2 可导入
    _ensure_v2_importable()

    try:
        from v2.core.infrastructure.repositories.cookie_repository import CookieRepository  # type: ignore
    except Exception as e:
        return False, None, None, f"导入 CookieRepository 失败: {e}"

    try:
        repo = CookieRepository(str(dst_dir))
        doc = await repo.save_from_raw(raw)
        info = doc.get("managed", {}) if isinstance(doc.get("managed"), dict) else {}
        dede_user_id = info.get("DedeUserID")
        target_path = Path(repo._file_path(str(dede_user_id)))  # 私有方法, 脚本内使用允许
        return True, str(dede_user_id), target_path, None
    except Exception as e:
        return False, None, None, f"保存失败: {e}"


def _resolve_dst_dir(dst_opt: str) -> Path:
    """
    根据参数解析目标目录: 
    - dst_opt == "auto" 时: 读取 v2 配置获取 storage.cookie_dir
    - 否则按显式路径解析
    """
    root = _project_root_from_this_file()
    if dst_opt == "auto":
        # 确保 v2 可导入
        _ensure_v2_importable()
        try:
            from v2.core.config.loader import load_config  # type: ignore
            cfg = load_config(None)
            d = Path(cfg.storage.cookie_dir)
            if not d.is_absolute():
                # 相对路径相对于 v2 包根目录(loader 中使用的是项目根)
                d = root / d
            return d
        except Exception as e:
            print(f"[WARN] 自动读取 v2 配置失败, 降级使用默认 ./data/cookie: {e}")
            return root / "data" / "cookie"
    else:
        d = Path(dst_opt)
        if not d.is_absolute():
            d = root / d
        return d


def _to_iso(ts: Optional[int | float | str]) -> Optional[str]:
    if ts is None:
        return None
    try:
        v = float(ts)
        # >1e11 视为毫秒
        if v > 1_000_000_000_00:
            dt = datetime.fromtimestamp(v / 1000)
        else:
            dt = datetime.fromtimestamp(v)
        return dt.isoformat()
    except Exception:
        return None


def _build_v2_like_raw(raw_v1: Dict[str, Any]) -> Dict[str, Any]:
    """将 v1 原始 JSON 转换为更贴近原生 v2 的 raw 结构。"""
    token_info = raw_v1.get("token_info", {}) or {}
    cookie_info = raw_v1.get("cookie_info", {}) or {}

    # 提取 mid(优先 token_info.mid, 其次 DedeUserID)
    mid: Optional[int] = None
    try:
        mid = int(token_info.get("mid")) if token_info.get("mid") is not None else None
    except Exception:
        mid = None
    if mid is None:
        try:
            cookies = cookie_info.get("cookies", [])
            for c in cookies:
                if isinstance(c, dict) and c.get("name") == "DedeUserID":
                    mid = int(c.get("value"))
                    break
        except Exception:
            mid = None

    raw_v2 = {
        "is_new": False,
        "mid": mid,
        "access_token": token_info.get("access_token"),
        "refresh_token": token_info.get("refresh_token"),
        "expires_in": token_info.get("expires_in"),
        "token_info": token_info,
        "cookie_info": cookie_info,
        # v2 原生样例中的 SSO/HINT, 若不存在则填默认
        "sso": [
            "https://passport.bilibili.com/api/v2/sso",
            "https://passport.biligame.com/api/v2/sso",
            "https://passport.bigfunapp.cn/api/v2/sso",
        ],
        "hint": "",
    }

    # 不保留 _cookiemgmt 于 raw 中(转由 managed 承载)
    return raw_v2


def _build_managed_for_v2(raw_v2: Dict[str, Any], legacy: Dict[str, Any]) -> Dict[str, Any]:
    """根据 v2 raw 与 v1 的 _cookiemgmt 构建 managed 字段。"""
    # 复用仓库的静态方法生成 header_string
    # 注意: 这里不调用 save_from_raw, 避免在 raw 中保留 _cookiemgmt
    try:
        from v2.core.infrastructure.repositories.cookie_repository import CookieRepository  # type: ignore
        cookie_map = CookieRepository._extract_cookie_map(raw_v2)
        header_str = CookieRepository._build_header_string(cookie_map)
    except Exception:
        # 兜底: 无需严格失败；若导入失败则直接拼接常用键
        cookies = raw_v2.get("cookie_info", {}).get("cookies", [])
        cmap: Dict[str, str] = {}
        for c in cookies:
            if isinstance(c, dict):
                name = c.get("name")
                val = c.get("value")
                if name:
                    cmap[str(name)] = str(val or "")
        parts = []
        for key in ["SESSDATA", "bili_jct", "buvid3", "buvid4", "DedeUserID", "DedeUserID__ckMd5"]:
            parts.append(f"{key}={cmap.get(key, '')}")
        header_str = "; ".join(parts)

    # DedeUserID
    dede_user_id = None
    for c in raw_v2.get("cookie_info", {}).get("cookies", []):
        if isinstance(c, dict) and c.get("name") == "DedeUserID":
            dede_user_id = str(c.get("value"))
            break

    # 状态映射
    def _map_status(val: Optional[str], cookie_valid: Optional[bool]) -> str:
        if val:
            v = str(val).lower()
            if v in {"valid", "ok"}:
                return "valid"
            if v in {"invalid", "bad"}:
                return "invalid"
            if v in {"expired"}:
                return "expired"
        if cookie_valid is not None:
            return "valid" if bool(cookie_valid) else "invalid"
        return "unknown"

    def _map_refresh(val: Optional[str]) -> str:
        if not val:
            return "success"
        v = str(val).lower()
        if v in {"success", "ok"}:
            return "success"
        if v in {"failed", "error"}:
            return "failed"
        if v in {"pending"}:
            return "pending"
        if v in {"not_needed", "none"}:
            return "not_needed"
        return "pending"

    # username 映射: 若是 DedeUserID、或 DedeUserID__ckMd5、或 16位十六进制(常见 ckMd5), 则视为“无真实用户名”, 留空
    legacy_username = legacy.get("username")
    username_out: Optional[str] = None
    if isinstance(legacy_username, str) and legacy_username.strip():
        try:
            ckmd5 = cookie_map.get("DedeUserID__ckMd5")
            dede = cookie_map.get("DedeUserID")
        except Exception:
            ckmd5 = None
            dede = None
        hex16 = bool(re.fullmatch(r"[0-9a-f]{16}", legacy_username))
        if legacy_username == ckmd5 or legacy_username == dede or hex16:
            username_out = None
        else:
            username_out = legacy_username
    else:
        username_out = None

    managed = {
        "DedeUserID": dede_user_id or "",
        "update_time": _to_iso(legacy.get("update_time")) or datetime.now().isoformat(),
        "last_check_time": _to_iso(legacy.get("last_check_time")),
        "last_refresh_time": _to_iso(legacy.get("last_refresh_time")) or datetime.now().isoformat(),
        "refresh_status": _map_refresh(legacy.get("refresh_status")),
        "error_message": (legacy.get("error_message") if legacy.get("error_message") is not None else None),
        "header_string": header_str,
        "is_enabled": bool(legacy.get("is_enabled", True)),
        "status": _map_status(legacy.get("status"), legacy.get("cookie_valid")),
        "username": username_out,
    }
    return managed


async def migrate(src_dir: Path, dst_dir: Path, ids: Optional[List[str]] = None, dry_run: bool = True, overwrite: bool = False, conform_raw: bool = True) -> Dict[str, Any]:
    dst_dir.mkdir(parents=True, exist_ok=True)

    files = _find_v1_files(src_dir, ids)
    total = len(files)
    migrated = 0
    skipped = 0
    errors: List[Dict[str, Any]] = []

    for fp in files:
        raw = _safe_load_json(fp)
        if raw is None:
            errors.append({"file": str(fp), "error": "解析失败"})
            continue

        dede_user_id = _extract_dede_user_id(raw)
        if not dede_user_id:
            errors.append({"file": str(fp), "error": "缺少 DedeUserID"})
            continue

        target_path = dst_dir / f"{dede_user_id}.json"
        if target_path.exists() and not overwrite:
            print(f"[SKIP] 目标已存在(未开启覆盖): {target_path}")
            skipped += 1
            continue

        if dry_run:
            # 仅预览
            print(f"[DRY-RUN] {fp.name} -> {target_path}")
            migrated += 1
        else:
            if conform_raw:
                # 构建 v2-like raw 与 managed, 并直接写入文件
                legacy = raw.get("_cookiemgmt", {}) if isinstance(raw.get("_cookiemgmt", {}), dict) else {}
                raw_v2 = _build_v2_like_raw(raw)
                managed = _build_managed_for_v2(raw_v2, legacy)
                doc = {"raw": raw_v2, "managed": managed}
                try:
                    with open(target_path, "w", encoding="utf-8") as f:
                        json.dump(doc, f, ensure_ascii=False, indent=2)
                    print(f"[OK] {fp.name} -> {target_path}")
                    migrated += 1
                except Exception as e:
                    errors.append({"file": str(fp), "error": f"写入失败: {e}"})
                    continue
            else:
                ok, uid, out_path, err = await _save_with_repo(raw, dst_dir)
                if not ok:
                    errors.append({"file": str(fp), "error": err or "未知错误"})
                    continue
                print(f"[OK] {fp.name} -> {out_path}")
                migrated += 1

    return {
        "ok": True,
        "total": total,
        "migrated": migrated,
        "skipped": skipped,
        "errors": errors,
        "src": str(src_dir),
        "dst": str(dst_dir),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="迁移 v1 Cookie JSON 到 v2 格式")
    parser.add_argument("--src", type=str, default="./v1/data/cookie", help="v1 源目录(默认 ./v1/data/cookie)")
    parser.add_argument("--dst", type=str, default="auto", help="v2 目标目录(auto 按配置解析, 或显式路径如 ./v2/data/cookie)")
    parser.add_argument("--ids", type=str, nargs="*", default=None, help="仅迁移指定 DedeUserID 列表(可选)")
    parser.add_argument("--dry-run", type=lambda x: str(x).lower() in {"1","true","yes","y"}, default=True, help="是否 dry-run(默认 true)")
    parser.add_argument("--overwrite", type=lambda x: str(x).lower() in {"1","true","yes","y"}, default=False, help="是否覆盖已有文件(默认 false)")
    parser.add_argument("--conform-raw", type=lambda x: str(x).lower() in {"1","true","yes","y"}, default=True, help="是否将 raw 映射为更接近原生 v2 的结构(默认 true)")
    return parser.parse_args()


def main():
    args = parse_args()
    root = _project_root_from_this_file()
    
    # 解析 src
    src_input = Path(args.src)
    if src_input.is_absolute():
        src_dir = src_input
    else:
        # 优先尝试相对于当前工作目录
        cwd_src = Path.cwd() / src_input
        if cwd_src.exists():
            src_dir = cwd_src
        else:
            # 否则尝试相对于项目根目录 (v2 的父目录)
            # 假设 v1 在 v2 的同级目录
            project_root = root.parent
            proj_src = project_root / src_input
            if proj_src.exists():
                src_dir = proj_src
            else:
                # 最后尝试相对于 v2 根目录
                src_dir = root / src_input

    dst_dir = _resolve_dst_dir(args.dst)

    print(f"[INFO] src={src_dir}")
    print(f"[INFO] dst={dst_dir} (dry-run={args.dry_run}, overwrite={args.overwrite})")

    result = asyncio.run(migrate(src_dir, dst_dir, ids=args.ids, dry_run=args.dry_run, overwrite=args.overwrite, conform_raw=args.conform_raw))
    print("\n===== 迁移摘要 =====")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()