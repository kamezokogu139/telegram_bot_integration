"""
Управление списком админов через JSON-файл.
Owner задаётся вручную в admins.json.
"""
import json
import os

from config import ADMINS_FILE


def _read() -> dict:
    if os.path.exists(ADMINS_FILE):
        with open(ADMINS_FILE, "r") as f:
            return json.load(f)
    return {"owner": None, "admins": []}


def _write(data: dict) -> None:
    with open(ADMINS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_owner() -> int | None:
    return _read().get("owner")


def is_admin(user_id: int) -> bool:
    data = _read()
    return user_id == data.get("owner") or user_id in data.get("admins", [])


def is_owner(user_id: int) -> bool:
    return _read().get("owner") == user_id


def add_admin(user_id: int) -> bool:
    data = _read()
    if user_id in data["admins"]:
        return False
    data["admins"].append(user_id)
    _write(data)
    return True


def remove_admin(user_id: int) -> bool:
    data = _read()
    if user_id == data.get("owner"):
        return False  # owner нельзя удалить
    if user_id not in data["admins"]:
        return False
    data["admins"].remove(user_id)
    _write(data)
    return True


def list_admins() -> tuple[int | None, list[int]]:
    data = _read()
    return data.get("owner"), data.get("admins", [])
