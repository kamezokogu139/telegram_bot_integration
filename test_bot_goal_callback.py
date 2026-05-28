import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import bot


class _FakeCallbackQuery:
    def __init__(self, data):
        self.data = data
        self.edited_messages = []
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edited_messages.append((text, kwargs))


class _FakeBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)


def _make_update(query):
    return SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123, username="tester", first_name="Test"),
        effective_chat=SimpleNamespace(id=456),
    )


def _make_context():
    return SimpleNamespace(
        user_data={
            "pending_postback": {
                "session_id": "current",
                "click_id": "click-1",
                "secure": "secure",
                "pid": "108",
                "offer_id": "4837",
                "goals": [{"value": "1", "title": "Registration", "status": 1}],
            }
        },
        bot=_FakeBot(),
    )


class GoalCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_payment_goal_status_for_numeric_registration_goal(self):
        query = _FakeCallbackQuery("goal_pick_current_0")
        context = _make_context()
        calls = []

        def fake_send_postback(click_id, secure, goal, status, pid):
            calls.append((click_id, secure, goal, status, pid))
            return True, "ok"

        with (
            patch.object(bot, "send_postback", fake_send_postback),
            patch.object(bot, "log_postback"),
        ):
            await bot.goal_callback(_make_update(query), context)

        self.assertEqual(calls, [("click-1", "secure", "1", 1, "108")])

    async def test_goal_callback_consumes_pending_before_sending_postback(self):
        query = _FakeCallbackQuery("goal_pick_current_0")
        context = _make_context()
        calls = []

        def fake_send_postback(click_id, secure, goal, status, pid):
            self.assertNotIn("pending_postback", context.user_data)
            calls.append((click_id, secure, goal, status, pid))
            return True, "ok"

        with (
            patch.object(bot, "send_postback", fake_send_postback),
            patch.object(bot, "log_postback"),
        ):
            await bot.goal_callback(_make_update(query), context)

        self.assertEqual(calls, [("click-1", "secure", "1", 1, "108")])

    async def test_rejects_stale_goal_callback_without_consuming_current_pending(self):
        query = _FakeCallbackQuery("goal_pick_old_0")
        context = _make_context()
        calls = []

        with (
            patch.object(bot, "send_postback", lambda *args: calls.append(args)),
            patch.object(bot, "log_postback"),
        ):
            await bot.goal_callback(_make_update(query), context)

        self.assertEqual(calls, [])
        self.assertIn("pending_postback", context.user_data)
        self.assertIn("устарела", query.edited_messages[0][0])

    async def test_rejects_legacy_cancel_callback_without_consuming_current_pending(self):
        query = _FakeCallbackQuery("goal_cancel")
        context = _make_context()

        await bot.goal_callback(_make_update(query), context)

        self.assertIn("pending_postback", context.user_data)
        self.assertIn("устарела", query.edited_messages[0][0])


class CancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_clears_pending_postback(self):
        message = SimpleNamespace(
            text="/cancel",
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(message=message)
        context = _make_context()

        await bot.cancel(update, context)

        self.assertNotIn("pending_postback", context.user_data)


if __name__ == "__main__":
    unittest.main()
