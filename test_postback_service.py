import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import postback_service


class _FakeAffiseResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "status": 1,
            "offer": {
                "hash_password": "sec&ret=2",
                "payments": [
                    {"goal": 1, "title": "Registration"},
                    {"goal": "dep&osit tier=1", "title": "Deposit"},
                ],
            },
        }


class _FakeAffiseClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None):
        return _FakeAffiseResponse()


class _FakePostbackResponse:
    status_code = 200

    def json(self):
        return {"status": 1}


class _FakePostbackClient:
    requested_url = None

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url):
        type(self).requested_url = url
        return _FakePostbackResponse()


class OfferGoalParsingTests(unittest.TestCase):
    def test_payment_goals_include_inferred_status(self):
        goals = postback_service._parse_offer_goals(
            {
                "payments": [
                    {"goal": 1, "title": "Registration"},
                    {"goal": "dep&osit tier=1", "title": "Deposit"},
                ],
            }
        )

        self.assertEqual(
            goals,
            [
                {
                    "id": "payment-0",
                    "title": "Registration",
                    "value": "1",
                    "status": 1,
                },
                {
                    "id": "payment-1",
                    "title": "Deposit",
                    "value": "dep&osit tier=1",
                    "status": 2,
                },
            ],
        )


class SendPostbackTests(unittest.TestCase):
    def test_send_postback_url_encodes_dynamic_query_values(self):
        with patch.object(postback_service.httpx, "Client", _FakePostbackClient):
            success, _ = postback_service.send_postback(
                clickid="clk&id=1",
                secure="sec&ret=2",
                goal="dep&osit tier=1",
                status=2,
                pid="42&bad=1",
            )

        self.assertTrue(success)
        parsed = urlparse(_FakePostbackClient.requested_url)
        params = parse_qs(parsed.query)

        self.assertEqual(params["clickid"], ["clk&id=1"])
        self.assertEqual(params["secure"], ["sec&ret=2"])
        self.assertEqual(params["goal"], ["dep&osit tier=1"])
        self.assertEqual(params["status"], ["2"])
        self.assertEqual(params["action_id"], ["TEST_42&bad=1"])
        self.assertNotIn("id", params)
        self.assertNotIn("ret", params)
        self.assertNotIn("bad", params)


class BuildAdvertiserPostbackUrlsTests(unittest.TestCase):
    def test_uses_offer_payment_goals_and_encodes_query_values(self):
        with patch.object(postback_service.httpx, "Client", _FakeAffiseClient):
            url_reg, url_dep, error = postback_service.build_postback_urls_for_advertiser("4837")

        self.assertEqual(error, "")

        reg_params = parse_qs(urlparse(url_reg).query)
        dep_params = parse_qs(urlparse(url_dep).query)

        self.assertEqual(reg_params["clickid"], ["{adv_click_id}"])
        self.assertEqual(reg_params["secure"], ["sec&ret=2"])
        self.assertEqual(reg_params["goal"], ["1"])
        self.assertEqual(reg_params["status"], ["1"])
        self.assertNotIn("ret", reg_params)

        self.assertEqual(dep_params["clickid"], ["{adv_click_id}"])
        self.assertEqual(dep_params["secure"], ["sec&ret=2"])
        self.assertEqual(dep_params["goal"], ["dep&osit tier=1"])
        self.assertEqual(dep_params["status"], ["2"])
        self.assertNotIn("osit tier", dep_params)


if __name__ == "__main__":
    unittest.main()
