import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import postback_service


class ParseOfferGoalsTests(unittest.TestCase):
    def test_numeric_registration_goal_keeps_registration_status(self):
        goals = postback_service._parse_offer_goals({
            "payments": [
                {"goal": "1", "title": "Registration"},
                {"goal": "2", "title": "Deposit"},
            ]
        })

        self.assertEqual(
            [
                {"value": "1", "status": 1},
                {"value": "2", "status": 2},
            ],
            [{"value": goal["value"], "status": goal["status"]} for goal in goals],
        )


class SendPostbackTests(unittest.TestCase):
    def test_send_postback_url_encodes_dynamic_query_values(self):
        captured_urls = []

        class FakeResponse:
            status_code = 200

            def json(self):
                return {"status": 1}

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def get(self, url):
                captured_urls.append(url)
                return FakeResponse()

        with patch.object(postback_service.httpx, "Client", FakeClient):
            success, _ = postback_service.send_postback(
                "click 1",
                "sec&ret",
                "dep&osit",
                2,
                "pid 108",
            )

        self.assertTrue(success)
        parsed = urlparse(captured_urls[0])
        self.assertEqual(
            {
                "clickid": ["click 1"],
                "secure": ["sec&ret"],
                "goal": ["dep&osit"],
                "status": ["2"],
                "action_id": ["TEST_pid 108"],
            },
            parse_qs(parsed.query),
        )


class AdvertiserPostbackUrlTests(unittest.TestCase):
    def test_advertiser_urls_use_offer_payment_goals_and_statuses(self):
        offer_details = (
            "secure&value",
            [
                {"value": "1", "title": "Registration", "status": 1},
                {"value": "2", "title": "Deposit", "status": 2},
            ],
            "",
        )
        with (
            patch.object(postback_service, "get_offer_details", return_value=offer_details),
            patch.object(postback_service, "get_offer_secure", return_value=("secure&value", "")),
        ):
            registration_url, deposit_url, error = postback_service.build_postback_urls_for_advertiser("192")

        self.assertEqual("", error)

        registration_query = parse_qs(urlparse(registration_url).query)
        self.assertEqual(["{adv_click_id}"], registration_query["clickid"])
        self.assertEqual(["secure&value"], registration_query["secure"])
        self.assertEqual(["1"], registration_query["goal"])
        self.assertEqual(["1"], registration_query["status"])

        deposit_query = parse_qs(urlparse(deposit_url).query)
        self.assertEqual(["2"], deposit_query["goal"])
        self.assertEqual(["2"], deposit_query["status"])


if __name__ == "__main__":
    unittest.main()
