import unittest

from postback_service import _parse_offer_goals


class ParseOfferGoalsTests(unittest.TestCase):
    def test_numeric_registration_payment_goal_gets_registration_status(self):
        goals = _parse_offer_goals({
            "payments": [
                {"goal": 1, "title": "Registration"},
                {"goal": 2, "title": "Deposit"},
            ],
        })

        self.assertEqual(goals[0]["value"], "1")
        self.assertEqual(goals[0].get("status"), 1)
        self.assertEqual(goals[1]["value"], "2")
        self.assertEqual(goals[1].get("status"), 2)


if __name__ == "__main__":
    unittest.main()
