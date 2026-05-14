import unittest
from types import SimpleNamespace
from unittest.mock import patch

import bot


class FakeQuery:
    def __init__(self, data: str):
        self.data = data
        self.answered = False
        self.edited_text = None
        self.edit_kwargs = None

    async def answer(self, *args, **kwargs):
        self.answered = True

    async def edit_message_text(self, text, **kwargs):
        self.edited_text = text
        self.edit_kwargs = kwargs


class FakeBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)


class GoalCallbackTests(unittest.IsolatedAsyncioTestCase):
    def _make_update(self, callback_data: str):
        return SimpleNamespace(
            callback_query=FakeQuery(callback_data),
            effective_user=SimpleNamespace(id=123, username="tester", first_name="Test"),
            effective_chat=SimpleNamespace(id=456),
        )

    def _make_context(self):
        return SimpleNamespace(
            user_data={
                "pending_postback": {
                    "click_id": "click-B",
                    "secure": "secure-B",
                    "pid": "108",
                    "offer_id": "192",
                    "callback_token": "currenttoken",
                    "goals": [
                        {"title": "Deposit", "value": "deposit"},
                    ],
                }
            },
            bot=FakeBot(),
        )

    async def test_goal_callback_rejects_unbound_old_keyboard_without_sending(self):
        update = self._make_update(f"{bot.CB_GOAL_PREFIX}0")
        context = self._make_context()
        send_calls = []

        with (
            patch.object(bot, "send_postback", side_effect=lambda *args: send_calls.append(args) or (True, "ok")),
            patch.object(bot, "log_postback"),
        ):
            await bot.goal_callback(update, context)

        self.assertEqual(send_calls, [])
        self.assertIn("pending_postback", context.user_data)
        self.assertIsNotNone(update.callback_query.edited_text)

    async def test_goal_callback_sends_only_for_matching_session_token(self):
        update = self._make_update(f"{bot.CB_GOAL_PREFIX}currenttoken_0")
        context = self._make_context()
        send_calls = []

        with (
            patch.object(bot, "send_postback", side_effect=lambda *args: send_calls.append(args) or (True, "ok")),
            patch.object(bot, "log_postback"),
        ):
            await bot.goal_callback(update, context)

        self.assertEqual(send_calls, [("click-B", "secure-B", "deposit", 2, "108")])
        self.assertNotIn("pending_postback", context.user_data)


if __name__ == "__main__":
    unittest.main()
