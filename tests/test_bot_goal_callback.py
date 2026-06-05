import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import bot


class FakeQuery:
    def __init__(self, data: str, edit_delay: float = 0, on_edit=None):
        self.data = data
        self.edit_delay = edit_delay
        self.on_edit = on_edit
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        if self.on_edit:
            self.on_edit()
        if self.edit_delay:
            await asyncio.sleep(self.edit_delay)
        self.edits.append((text, kwargs))


class FakeBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)


def make_context(session_id: str = "session1"):
    return SimpleNamespace(
        bot=FakeBot(),
        user_data={
            "pending_postback": {
                "session_id": session_id,
                "click_id": "click12345",
                "secure": "secure123",
                "pid": "108",
                "offer_id": "192",
                "goals": [{"title": "Registration", "value": "registration"}],
            }
        },
    )


def make_update(callback_data: str, edit_delay: float = 0, on_edit=None):
    return SimpleNamespace(
        callback_query=FakeQuery(callback_data, edit_delay=edit_delay, on_edit=on_edit),
        effective_chat=SimpleNamespace(id=777),
        effective_user=SimpleNamespace(id=42, username="tester", first_name="Test"),
    )


class GoalCallbackSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_goal_callback_does_not_send_current_pending(self):
        context = make_context(session_id="newer")
        update = make_update(f"{bot.CB_GOAL_PREFIX}0")
        send_calls = []

        async def fake_to_thread(func, *args):
            send_calls.append(args)
            return True, "ok"

        with (
            patch("bot.is_approved", return_value=True),
            patch("bot.asyncio.to_thread", side_effect=fake_to_thread),
            patch("bot.log_postback"),
        ):
            await bot.goal_callback(update, context)

        self.assertEqual(send_calls, [])
        self.assertIn("pending_postback", context.user_data)

    async def test_concurrent_goal_callbacks_for_session_send_once(self):
        context = make_context(session_id="session1")
        first_update = make_update(f"{bot.CB_GOAL_PREFIX}session1_0", edit_delay=0.01)
        second_update = make_update(f"{bot.CB_GOAL_PREFIX}session1_0", edit_delay=0.01)
        send_calls = []

        async def fake_to_thread(func, *args):
            send_calls.append(args)
            await asyncio.sleep(0.01)
            return True, "ok"

        with (
            patch("bot.is_approved", return_value=True),
            patch("bot.asyncio.to_thread", side_effect=fake_to_thread),
            patch("bot.log_postback"),
        ):
            await asyncio.gather(
                bot.goal_callback(first_update, context),
                bot.goal_callback(second_update, context),
            )

        self.assertEqual(len(send_calls), 1)
        self.assertNotIn("pending_postback", context.user_data)

    async def test_invalid_index_does_not_clear_newer_pending_created_during_edit(self):
        context = make_context(session_id="session1")
        newer_pending = {
            "session_id": "session2",
            "click_id": "click67890",
            "secure": "secure456",
            "pid": "108",
            "offer_id": "193",
            "goals": [{"title": "Deposit", "value": "deposit"}],
        }

        def replace_with_newer_pending():
            context.user_data["pending_postback"] = newer_pending

        update = make_update(
            f"{bot.CB_GOAL_PREFIX}session1_99",
            edit_delay=0.01,
            on_edit=replace_with_newer_pending,
        )

        with (
            patch("bot.is_approved", return_value=True),
            patch("bot.log_postback"),
        ):
            await bot.goal_callback(update, context)

        self.assertEqual(context.user_data["pending_postback"]["session_id"], "session2")
