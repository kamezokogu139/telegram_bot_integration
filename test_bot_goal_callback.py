import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import bot


class _FakeQuery:
    def __init__(self, data: str):
        self.data = data
        self.message = SimpleNamespace(text="goal picker")
        self.edits: list[str] = []

    async def answer(self, *args, **kwargs):
        await asyncio.sleep(0)

    async def edit_message_text(self, text: str, *args, **kwargs):
        self.edits.append(text)


class _FakeContext:
    def __init__(self):
        self.user_data = {
            "pending_postback": {
                "click_id": "click-12345",
                "secure": "secure-token",
                "pid": "108",
                "offer_id": "4837",
                "goals": [{"value": "deposit", "title": "Deposit"}],
            }
        }
        self.bot = SimpleNamespace(send_message=self._send_message)

    async def _send_message(self, *args, **kwargs):
        return None


def _fake_update(query: _FakeQuery):
    return SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123, username="tester", first_name="Test"),
        effective_chat=SimpleNamespace(id=456),
    )


class GoalCallbackConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_goal_callbacks_send_postback_once(self):
        context = _FakeContext()
        calls: list[tuple[str, str, str, int, str]] = []

        def fake_send_postback(click_id, secure, goal, status, pid):
            calls.append((click_id, secure, goal, status, pid))
            time.sleep(0.05)
            return True, "ok"

        queries = [_FakeQuery("goal_pick_0"), _FakeQuery("goal_pick_0")]
        updates = [_fake_update(query) for query in queries]

        with (
            patch.object(bot, "send_postback", side_effect=fake_send_postback),
            patch.object(bot, "log_postback"),
        ):
            await asyncio.gather(
                bot.goal_callback(updates[0], context),
                bot.goal_callback(updates[1], context),
            )

        self.assertEqual(
            1,
            len(calls),
            "Only one postback should be sent for duplicate callbacks from the same keyboard.",
        )
        self.assertNotIn("pending_postback", context.user_data)


if __name__ == "__main__":
    unittest.main()
