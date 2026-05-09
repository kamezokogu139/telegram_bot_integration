import unittest
from types import SimpleNamespace
from unittest.mock import patch

import bot


class FakeCallbackQuery:
    def __init__(self, data: str):
        self.data = data
        self.edited_messages = []

    async def answer(self, *args, **kwargs):
        return None

    async def edit_message_text(self, text, *args, **kwargs):
        self.edited_messages.append((text, args, kwargs))


class FakeBot:
    def __init__(self):
        self.sent_messages = []

    async def send_message(self, *args, **kwargs):
        self.sent_messages.append((args, kwargs))


class GoalCallbackStatusTest(unittest.IsolatedAsyncioTestCase):
    async def test_numeric_registration_goal_uses_registration_status(self):
        query = FakeCallbackQuery(f"{bot.CB_GOAL_PREFIX}0")
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(
                id=123,
                username="tester",
                first_name="Test",
            ),
            effective_chat=SimpleNamespace(id=456),
        )
        context = SimpleNamespace(
            user_data={
                "pending_postback": {
                    "click_id": "click123456",
                    "secure": "secure",
                    "pid": "108",
                    "offer_id": "42",
                    "goals": [
                        {
                            "value": "1",
                            "title": "Registration",
                            "status": 1,
                        },
                    ],
                }
            },
            bot=FakeBot(),
        )

        captured = {}

        def fake_send_postback(click_id, secure, goal, status, pid):
            captured.update(
                {
                    "click_id": click_id,
                    "secure": secure,
                    "goal": goal,
                    "status": status,
                    "pid": pid,
                }
            )
            return True, "ok"

        with patch.object(bot, "send_postback", side_effect=fake_send_postback), patch.object(
            bot, "log_postback"
        ):
            await bot.goal_callback(update, context)

        self.assertEqual(captured["goal"], "1")
        self.assertEqual(captured["status"], 1)


if __name__ == "__main__":
    unittest.main()
