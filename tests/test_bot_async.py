import unittest
from unittest.mock import patch

import bot


class FakeMessage:
    def __init__(self, text: str):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class FakeUser:
    id = 123
    username = "tester"
    first_name = "Test"


class FakeUpdate:
    def __init__(self, text: str):
        self.message = FakeMessage(text)
        self.effective_user = FakeUser()


class FakeContext:
    def __init__(self):
        self.user_data = {"action": bot.CB_REG}


class ProcessLinkAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_process_link_runs_blocking_postback_steps_in_threads(self):
        threaded_calls = []

        async def fake_to_thread(func, *args, **kwargs):
            threaded_calls.append(func.__name__)
            return func(*args, **kwargs)

        def fake_extract(link):
            return "click12345", "4837", "108", ""

        def fake_secure(offer_id):
            return "secure-token", ""

        def fake_send(clickid, secure, goal, status, pid):
            return True, "ok"

        update = FakeUpdate("https://trk.xplink/click?pid=108&offer_id=4837")
        context = FakeContext()

        with (
            patch.object(bot.asyncio, "to_thread", side_effect=fake_to_thread),
            patch.object(bot, "extract_clickid_from_redirect", side_effect=fake_extract),
            patch.object(bot, "get_offer_secure", side_effect=fake_secure),
            patch.object(bot, "send_postback", side_effect=fake_send),
            patch.object(bot, "log_postback"),
        ):
            await bot.process_link(update, context)

        self.assertEqual(
            threaded_calls,
            ["fake_extract", "fake_secure", "fake_send"],
        )


if __name__ == "__main__":
    unittest.main()
