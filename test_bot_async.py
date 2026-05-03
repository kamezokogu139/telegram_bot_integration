import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import bot


class FakeMessage:
    def __init__(self, text: str):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))
        await asyncio.sleep(0)


class ProcessLinkAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_process_link_does_not_block_event_loop_during_external_calls(self):
        message = FakeMessage("https://partner.example/link")
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(
                id=123,
                username="tester",
                first_name="Test",
            ),
        )
        context = SimpleNamespace(user_data={})

        def slow_extract(_link):
            time.sleep(0.05)
            return "clickid123", "456", "108", ""

        def slow_secure(_offer_id):
            time.sleep(0.05)
            return "secure", ""

        def slow_send(_clickid, _secure, _goal, _status, _pid):
            time.sleep(0.05)
            return True, "ok"

        with (
            patch.object(bot, "extract_clickid_from_redirect", side_effect=slow_extract),
            patch.object(bot, "get_offer_secure", side_effect=slow_secure),
            patch.object(bot, "send_postback", side_effect=slow_send),
            patch.object(bot, "log_postback"),
        ):
            task = asyncio.create_task(bot.process_link(update, context))
            start = time.perf_counter()
            await asyncio.sleep(0.01)
            elapsed = time.perf_counter() - start
            await task

        self.assertLess(
            elapsed,
            0.04,
            "process_link blocked the event loop while running external HTTP work",
        )


if __name__ == "__main__":
    unittest.main()
