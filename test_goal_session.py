import unittest

import bot
from telegram.ext import CommandHandler, ConversationHandler


class GoalSessionCallbackTests(unittest.TestCase):
    def test_goal_keyboard_binds_buttons_to_session_id(self):
        keyboard = bot._build_goals_keyboard(
            [{"title": "Registration", "value": "registration"}],
            "session-a",
        )

        rows = keyboard.inline_keyboard

        self.assertEqual(rows[0][0].callback_data, "goal_pick_session-a_0")
        self.assertEqual(rows[1][0].callback_data, "goal_cancel_session-a")

    def test_stale_goal_callback_is_rejected_before_using_current_pending(self):
        pending = {
            "session_id": "session-b",
            "goals": [{"title": "Deposit", "value": "deposit"}],
        }

        parsed = bot._parse_goal_callback_data("goal_pick_session-a_0", pending)

        self.assertEqual(parsed["action"], "stale")

    def test_callback_is_rejected_when_pending_has_no_session_id(self):
        pending = {
            "goals": [{"title": "Deposit", "value": "deposit"}],
        }

        parsed = bot._parse_goal_callback_data("goal_pick__0", pending)

        self.assertEqual(parsed["action"], "stale")


class HandlerRegistrationTests(unittest.TestCase):
    def test_global_cancel_is_registered_after_conversation_handlers(self):
        class FakeApplication:
            def __init__(self):
                self.handlers = []

            def add_handler(self, handler):
                self.handlers.append(handler)

        app = FakeApplication()

        bot._register_handlers(app)

        conversation_indexes = [
            i for i, handler in enumerate(app.handlers)
            if isinstance(handler, ConversationHandler)
        ]
        global_cancel_indexes = [
            i for i, handler in enumerate(app.handlers)
            if isinstance(handler, CommandHandler) and "cancel" in handler.commands
        ]

        self.assertTrue(conversation_indexes)
        self.assertTrue(global_cancel_indexes)
        self.assertGreater(global_cancel_indexes[-1], max(conversation_indexes))


if __name__ == "__main__":
    unittest.main()
