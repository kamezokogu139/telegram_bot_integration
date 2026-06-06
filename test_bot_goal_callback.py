import asyncio
import time
import unittest
from unittest.mock import AsyncMock, patch

import bot


class _FakeUser:
    id = 123
    username = "tester"
    first_name = "Test"


class _FakeChat:
    id = 456


class _FakeQuery:
    def __init__(self, data):
        self.data = data
        self.answer = AsyncMock()
        self.edit_message_text = AsyncMock()


class _FakeUpdate:
    def __init__(self, data):
        self.callback_query = _FakeQuery(data)
        self.effective_user = _FakeUser()
        self.effective_chat = _FakeChat()


class _FakeContext:
    def __init__(self, pending):
        self.user_data = {"pending_postback": pending} if pending is not None else {}
        self.bot = type("FakeBot", (), {"send_message": AsyncMock()})()


def _pending_postback():
    return {
        "session_id": "active-session",
        "click_id": "click12345",
        "secure": "secure",
        "pid": "108",
        "offer_id": "4837",
        "goals": [{"title": "Registration", "value": "registration", "status": 1}],
    }


def _pending_numeric_registration():
    pending = _pending_postback()
    pending["goals"] = [{"title": "Registration payout", "value": "1", "status": 1}]
    return pending


class GoalCallbackSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_pending_goal_callback_does_not_overwrite_existing_message(self):
        context = _FakeContext(None)
        update = _FakeUpdate("goal_pick_active-session_0")

        with patch.object(bot, "send_postback") as send_postback:
            await bot.goal_callback(update, context)

        send_postback.assert_not_called()
        update.callback_query.edit_message_text.assert_not_called()

    async def test_rejects_legacy_goal_callback_without_consuming_current_pending(self):
        context = _FakeContext(_pending_postback())
        update = _FakeUpdate("goal_pick_0")

        with patch.object(bot, "send_postback") as send_postback:
            await bot.goal_callback(update, context)

        send_postback.assert_not_called()
        self.assertIn("pending_postback", context.user_data)

    async def test_rejects_mismatched_session_goal_callback_without_consuming_current_pending(self):
        context = _FakeContext(_pending_postback())
        update = _FakeUpdate("goal_pick_old-session_0")

        with patch.object(bot, "send_postback") as send_postback:
            await bot.goal_callback(update, context)

        send_postback.assert_not_called()
        self.assertIn("pending_postback", context.user_data)

    async def test_rejects_stale_cancel_callback_without_consuming_current_pending(self):
        context = _FakeContext(_pending_postback())
        update = _FakeUpdate("goal_cancel_old-session")

        with patch.object(bot, "send_postback") as send_postback:
            await bot.goal_callback(update, context)

        send_postback.assert_not_called()
        self.assertIn("pending_postback", context.user_data)

    async def test_accepts_goal_callback_only_for_matching_session(self):
        context = _FakeContext(_pending_postback())
        update = _FakeUpdate("goal_pick_active-session_0")

        with (
            patch.object(bot, "send_postback", return_value=(True, "ok")) as send_postback,
            patch.object(bot, "log_postback"),
        ):
            await bot.goal_callback(update, context)

        send_postback.assert_called_once_with("click12345", "secure", "registration", 1, "108")
        self.assertNotIn("pending_postback", context.user_data)

    async def test_uses_payment_status_for_selected_goal(self):
        context = _FakeContext(_pending_numeric_registration())
        update = _FakeUpdate("goal_pick_active-session_0")

        with (
            patch.object(bot, "send_postback", return_value=(True, "ok")) as send_postback,
            patch.object(bot, "log_postback"),
        ):
            await bot.goal_callback(update, context)

        send_postback.assert_called_once_with("click12345", "secure", "1", 1, "108")
        self.assertNotIn("pending_postback", context.user_data)

    async def test_concurrent_goal_callbacks_send_postback_once(self):
        context = _FakeContext(_pending_postback())
        update_one = _FakeUpdate("goal_pick_active-session_0")
        update_two = _FakeUpdate("goal_pick_active-session_0")
        calls = 0

        def slow_send_postback(*args):
            nonlocal calls
            calls += 1
            time.sleep(0.05)
            return True, "ok"

        with (
            patch.object(bot, "send_postback", side_effect=slow_send_postback),
            patch.object(bot, "log_postback"),
        ):
            await asyncio.gather(
                bot.goal_callback(update_one, context),
                bot.goal_callback(update_two, context),
            )

        self.assertEqual(calls, 1)
        self.assertNotIn("pending_postback", context.user_data)


if __name__ == "__main__":
    unittest.main()
