import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import bot


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.answer = AsyncMock()
        self.edit_message_text = AsyncMock()


def _update(callback_data):
    return SimpleNamespace(
        callback_query=FakeQuery(callback_data),
        effective_user=SimpleNamespace(id=42, username="tester", first_name="Test"),
        effective_chat=SimpleNamespace(id=100),
    )


def _context():
    return SimpleNamespace(
        user_data={
            "pending_postback": {
                "session_id": "current-session",
                "click_id": "click-1",
                "secure": "secure",
                "pid": "108",
                "offer_id": "192",
                "goals": [{"value": "1", "title": "Registration", "status": 1}],
            },
        },
        bot=SimpleNamespace(send_message=AsyncMock()),
    )


class GoalCallbackSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_stale_goal_callback_without_consuming_current_pending(self):
        context = _context()

        with patch.object(bot, "send_postback") as send_postback:
            await bot.goal_callback(_update("goal_pick_old-session_0"), context)

        send_postback.assert_not_called()
        self.assertIn("pending_postback", context.user_data)
        self.assertEqual(
            "current-session",
            context.user_data["pending_postback"]["session_id"],
        )

    async def test_uses_payment_status_for_selected_goal(self):
        context = _context()

        with (
            patch.object(bot, "send_postback", return_value=(True, "ok")) as send_postback,
            patch.object(bot, "log_postback"),
        ):
            await bot.goal_callback(_update("goal_pick_current-session_0"), context)

        send_postback.assert_called_once_with("click-1", "secure", "1", 1, "108")
        self.assertNotIn("pending_postback", context.user_data)

    async def test_concurrent_goal_callbacks_send_postback_once(self):
        context = _context()

        def slow_send_postback(*args):
            time.sleep(0.05)
            return True, "ok"

        with (
            patch.object(bot, "send_postback", side_effect=slow_send_postback) as send_postback,
            patch.object(bot, "log_postback"),
        ):
            await asyncio.gather(
                bot.goal_callback(_update("goal_pick_current-session_0"), context),
                bot.goal_callback(_update("goal_pick_current-session_0"), context),
            )

        send_postback.assert_called_once_with("click-1", "secure", "1", 1, "108")
        self.assertNotIn("pending_postback", context.user_data)


if __name__ == "__main__":
    unittest.main()
