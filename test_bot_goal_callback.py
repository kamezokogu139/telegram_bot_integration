import unittest
from types import SimpleNamespace
from unittest.mock import patch

import bot


class _FakeCallbackQuery:
    def __init__(self, data):
        self.data = data
        self.edited_messages = []

    async def answer(self, *args, **kwargs):
        return None

    async def edit_message_text(self, text, **kwargs):
        self.edited_messages.append((text, kwargs))


class _FakeBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)


class GoalCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_payment_goal_status_for_numeric_registration_goal(self):
        query = _FakeCallbackQuery("goal_pick_0")
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=123, username="tester", first_name="Test"),
            effective_chat=SimpleNamespace(id=456),
        )
        context = SimpleNamespace(
            user_data={
                "pending_postback": {
                    "click_id": "click-1",
                    "secure": "secure",
                    "pid": "108",
                    "offer_id": "4837",
                    "goals": [{"value": "1", "title": "Registration", "status": 1}],
                }
            },
            bot=_FakeBot(),
        )
        calls = []

        def fake_send_postback(click_id, secure, goal, status, pid):
            calls.append((click_id, secure, goal, status, pid))
            return True, "ok"

        with (
            patch.object(bot, "send_postback", fake_send_postback),
            patch.object(bot, "log_postback"),
        ):
            await bot.goal_callback(update, context)

        self.assertEqual(calls, [("click-1", "secure", "1", 1, "108")])


if __name__ == "__main__":
    unittest.main()
