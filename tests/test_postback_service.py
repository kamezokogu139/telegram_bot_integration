import unittest

from postback_service import _parse_offer_goals


class OfferGoalParsingTest(unittest.TestCase):
    def test_payment_registration_title_sets_registration_status_for_numeric_goal(self):
        goals = _parse_offer_goals(
            {
                "payments": [
                    {
                        "goal": "1",
                        "title": "Registration",
                        "goal_id": 10,
                    },
                ]
            }
        )

        self.assertEqual(goals[0]["value"], "1")
        self.assertEqual(goals[0]["status"], 1)


if __name__ == "__main__":
    unittest.main()
