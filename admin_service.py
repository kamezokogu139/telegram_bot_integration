"""
Управление владельцем и одобренными пользователями через JSON-файл.
Owner — единственный админ. Approved — пользователи, которым разрешено использовать бота.
"""
import json
import os
from datetime import datetime, timezone

from config import ADMINS_FILE, REQUEST_ACCESS_LOG_FILE, REQUEST_ACCESS_LIMIT_PER_DAY


def _read() -> dict:
    if os.path.exists(ADMINS_FILE):
        with open(ADMINS_FILE, "r") as f:
            data = json.load(f)
            # Миграция: если есть admins, добавляем owner в approved
            if "approved" not in data and "admins" in data:
                data["approved"] = list(set(data.get("admins", []) + ([data["owner"]] if data.get("owner") else []))
            return data
    return {"owner": None, "approved": []}


def _write(data: dict) -> None:
    with open(ADMINS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_owner() -> int | None:
    return _read().get("owner")


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
