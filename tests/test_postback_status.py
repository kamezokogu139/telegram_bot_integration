import unittest

from postback_service import infer_postback_status


class InferPostbackStatusTests(unittest.TestCase):
    def test_registration_goal_value_uses_registration_status(self):
        self.assertEqual(infer_postback_status("registration"), 1)

    def test_numeric_registration_goal_uses_registration_status_from_title(self):
        self.assertEqual(infer_postback_status("1", "Registration"), 1)

    def test_non_registration_goal_defaults_to_deposit_status(self):
        self.assertEqual(infer_postback_status("2", "Deposit"), 2)


if __name__ == "__main__":
    unittest.main()
