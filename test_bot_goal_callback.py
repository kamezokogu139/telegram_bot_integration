import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import bot


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.answer = AsyncMock()
        self.edit_message_text = AsyncMock()


class GoalCallbackSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_stale_goal_callback_without_consuming_current_pending(self):
        query = FakeQuery("goal_pick_old-session_0")
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=42, username="tester", first_name="Test"),
            effective_chat=SimpleNamespace(id=100),
        )
        context = SimpleNamespace(
            user_data={
                "pending_postback": {
                    "session_id": "current-session",
                    "click_id": "click-1",
                    "secure": "secure",
                    "pid": "108",
                    "offer_id": "192",
                    "goals": [{"value": "1", "title": "Registration", "status": 1}],
                }
            },
            bot=SimpleNamespace(send_message=AsyncMock()),
        )

        with patch.object(bot, "send_postback") as send_postback:
            await bot.goal_callback(update, context)

        send_postback.assert_not_called()
        self.assertIn("pending_postback", context.user_data)
        self.assertEqual("current-session", context.user_data["pending_postback"]["session_id"])

    async def test_uses_payment_status_for_selected_goal(self):
        query = FakeQuery("goal_pick_current-session_0")
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=42, username="tester", first_name="Test"),
            effective_chat=SimpleNamespace(id=100),
        )
        context = SimpleNamespace(
            user_data={
                "pending_postback": {
                    "session_id": "current-session",
                    "click_id": "click-1",
                    "secure": "secure",
                    "pid": "108",
                    "offer_id": "192",
                    "goals": [{"value": "1", "title": "Registration", "status": 1}],
                }
            },
            bot=SimpleNamespace(send_message=AsyncMock()),
        )

        with (
            patch.object(bot, "send_postback", return_value=(True, "ok")) as send_postback,
            patch.object(bot, "log_postback"),
        ):
            await bot.goal_callback(update, context)

        send_postback.assert_called_once_with("click-1", "secure", "1", 1, "108")
        self.assertNotIn("pending_postback", context.user_data)


if __name__ == "__main__":
    unittest.main()
