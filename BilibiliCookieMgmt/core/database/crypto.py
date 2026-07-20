from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet


def load_or_create_fernet(key_path: str | Path, database_path: str | Path) -> Fernet:
    """加载数据密钥；只有数据库尚不存在时才允许生成。"""
    key_file = Path(key_path)
    database_file = Path(database_path)

    if key_file.exists():
        try:
            return Fernet(key_file.read_bytes().strip())
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"无法读取数据加密密钥: {key_file}") from exc

    if database_file.exists():
        raise RuntimeError(f"数据库已存在但缺少加密密钥: {key_file}")

    key_file.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    with key_file.open("xb") as file:
        file.write(key)
    try:
        os.chmod(key_file, 0o600)
    except OSError:
        pass
    return Fernet(key)
