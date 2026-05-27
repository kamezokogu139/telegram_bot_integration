"""
Управление владельцем и одобренными пользователями через JSON-файл.
Owner — единственный админ. Approved — пользователи, которым разрешено использовать бота.
"""
import json
import os
import tempfile
from datetime import datetime, timezone

from config import ADMINS_FILE, REQUEST_ACCESS_LOG_FILE, REQUEST_ACCESS_LIMIT_PER_DAY


def _read() -> dict:
    if os.path.exists(ADMINS_FILE):
        try:
            with open(ADMINS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return {"owner": None, "approved": []}

        if not isinstance(data, dict):
            return {"owner": None, "approved": []}

        # Миграция: если есть admins, добавляем owner в approved
        if "approved" not in data and "admins" in data:
            admins_list = data.get("admins", [])
            if not isinstance(admins_list, list):
                admins_list = []
            owner_val = data.get("owner")
            if owner_val is not None:
                admins_list = list(set(admins_list + [owner_val]))
            data["approved"] = admins_list
        if not isinstance(data.get("approved", []), list):
            data["approved"] = []
        return data
    return {"owner": None, "approved": []}


def _write(data: dict) -> None:
    directory = os.path.dirname(ADMINS_FILE) or "."
    fd, tmp_path = tempfile.mkstemp(
        prefix=".admins.",
        suffix=".tmp",
        dir=directory,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, ADMINS_FILE)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def get_owner() -> int | None:
    return _read().get("owner")


def get_users_with_access() -> dict:
    """Возвращает {'owner': user_id, 'approved': [user_ids]} — все, у кого есть доступ."""
    data = _read()
    return {
        "owner": data.get("owner"),
        "approved": data.get("approved", []),
    }


def is_owner(user_id: int) -> bool:
    return _read().get("owner") == user_id


def is_admin(user_id: int) -> bool:
    """Админ = только владелец."""
    return is_owner(user_id)


def is_approved(user_id: int) -> bool:
    """Одобренный пользователь может использовать Reg/Dep."""
    data = _read()
    return user_id == data.get("owner") or user_id in data.get("approved", [])


def add_approved(user_id: int) -> bool:
    data = _read()
    approved = data.setdefault("approved", [])
    if user_id in approved:
        return False
    approved.append(user_id)
    _write(data)
    return True


def _read_access_log() -> dict:
    """Читает лог запросов доступа."""
    if os.path.exists(REQUEST_ACCESS_LOG_FILE):
        try:
            with open(REQUEST_ACCESS_LOG_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _write_access_log(data: dict) -> None:
    with open(REQUEST_ACCESS_LOG_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def count_requests_today(user_id: int) -> int:
    """Количество запросов доступа за сегодня (UTC)."""
    log = _read_access_log()
    today = _today_utc()
    user_log = log.get(str(user_id), [])
    return sum(1 for ts in user_log if ts[:10] == today)


def log_request_access(user_id: int) -> None:
    """Записывает запрос доступа."""
    log = _read_access_log()
    key = str(user_id)
    if key not in log:
        log[key] = []
    log[key].append(datetime.now(timezone.utc).isoformat())
    log[key] = log[key][-50:]  # храним последние 50 записей на пользователя
    _write_access_log(log)


def can_request_access(user_id: int) -> tuple[bool, int]:
    """Можно ли отправить запрос доступа. Возвращает (можно, использовано_сегодня)."""
    count = count_requests_today(user_id)
    return count < REQUEST_ACCESS_LIMIT_PER_DAY, count
