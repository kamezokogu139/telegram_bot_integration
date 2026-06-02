import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import bot


class _FakeCallbackQuery:
    def __init__(self, data):
        self.data = data
        self.messages = []

    async def answer(self):
        return None

    async def edit_message_text(self, text, **kwargs):
        self.messages.append(text)


class _FakeBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)


def _update(callback_data):
    return SimpleNamespace(
        callback_query=_FakeCallbackQuery(callback_data),
        effective_user=SimpleNamespace(id=123, username="alice", first_name="Alice"),
        effective_chat=SimpleNamespace(id=456),
    )


def _context(pending):
    return SimpleNamespace(user_data={"pending_postback": pending}, bot=_FakeBot())


def _pending():
    return {
        "click_id": "click-12345",
        "secure": "secure",
        "pid": "108",
        "offer_id": "4837",
        "goals": [
            {"title": "Registration", "value": "1"},
            {"title": "Deposit", "value": "dep"},
        ],
    }


class GoalCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_numeric_registration_goal_uses_registration_status(self):
        calls = []

        def fake_send_postback(click_id, secure, goal, status, pid):
            calls.append((click_id, secure, goal, status, pid))
            return True, "sent"

        with (
            patch.object(bot, "send_postback", fake_send_postback),
            patch.object(bot, "log_postback"),
        ):
            await bot.goal_callback(_update("goal_pick_0"), _context(_pending()))

        self.assertEqual(calls, [("click-12345", "secure", "1", 1, "108")])

    async def test_concurrent_goal_callbacks_send_postback_once(self):
        context = _context(_pending())
        calls = []

        def fake_send_postback(click_id, secure, goal, status, pid):
            calls.append((click_id, secure, goal, status, pid))
            time.sleep(0.05)
            return True, "sent"

        with (
            patch.object(bot, "send_postback", fake_send_postback),
            patch.object(bot, "log_postback"),
        ):
            await asyncio.gather(
                bot.goal_callback(_update("goal_pick_1"), context),
                bot.goal_callback(_update("goal_pick_1"), context),
            )

        self.assertEqual(len(calls), 1)
        self.assertNotIn("pending_postback", context.user_data)

    async def test_legacy_goal_callback_does_not_consume_active_pending_session(self):
        pending = _pending()
        pending["session_id"] = "current"
        context = _context(pending)
        calls = []

        def fake_send_postback(click_id, secure, goal, status, pid):
            calls.append((click_id, secure, goal, status, pid))
            return True, "sent"

        with (
            patch.object(bot, "send_postback", fake_send_postback),
            patch.object(bot, "log_postback"),
        ):
            await bot.goal_callback(_update("goal_pick_0"), context)

        self.assertEqual(calls, [])
        self.assertIs(context.user_data.get("pending_postback"), pending)

    async def test_legacy_cancel_callback_does_not_consume_active_pending_session(self):
        pending = _pending()
        pending["session_id"] = "current"
        context = _context(pending)

        with patch.object(bot, "send_postback") as send_postback:
            await bot.goal_callback(_update("goal_cancel"), context)

        send_postback.assert_not_called()
        self.assertIs(context.user_data.get("pending_postback"), pending)


if __name__ == "__main__":
    unittest.main()
