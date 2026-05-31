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
            ],
        })

        self.assertEqual(
            [
                {"value": "1", "status": 1},
                {"value": "2", "status": 2},
            ],
            [{"value": goal["value"], "status": goal["status"]} for goal in goals],
        )


class _FakePostbackResponse:
    status_code = 200

    def json(self):
        return {"status": 1}


class _RecordingPostbackClient:
    last_url = None

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, *args, **kwargs):
        type(self).last_url = url
        return _FakePostbackResponse()


class _FakeOfferResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "status": 1,
            "offer": {
                "hash_password": "sec+ret&hash",
                "payments": [
                    {"goal": 1, "title": "Registration payout"},
                    {"goal": "dep&main", "title": "Deposit payout"},
                ],
            },
        }


class _FakeOfferClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, *args, **kwargs):
        return _FakeOfferResponse()


class SendPostbackTests(unittest.TestCase):
    def test_send_postback_url_encodes_dynamic_query_values(self):
        with patch.object(postback_service.httpx, "Client", _RecordingPostbackClient):
            success, _ = postback_service.send_postback(
                clickid="clk+123&tail",
                secure="sec+ret&hash",
                goal="dep&main",
                status=2,
                pid="pid/108?x=1",
            )

        self.assertTrue(success)
        parsed = urlparse(_RecordingPostbackClient.last_url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        self.assertEqual(query["clickid"], ["clk+123&tail"])
        self.assertEqual(query["secure"], ["sec+ret&hash"])
        self.assertEqual(query["goal"], ["dep&main"])
        self.assertEqual(query["status"], ["2"])
        self.assertEqual(query["action_id"], ["TEST_pid/108?x=1"])


class BuildAdvertiserPostbackUrlTests(unittest.TestCase):
    def test_build_postback_urls_use_offer_payment_goals_and_encode_values(self):
        with patch.object(postback_service.httpx, "Client", _FakeOfferClient):
            url_reg, url_dep, error = postback_service.build_postback_urls_for_advertiser(
                "4837",
                pid="108",
            )

        self.assertEqual(error, "")
        self.assertIsNotNone(url_reg)
        self.assertIsNotNone(url_dep)

        reg_query = parse_qs(urlparse(url_reg).query, keep_blank_values=True)
        dep_query = parse_qs(urlparse(url_dep).query, keep_blank_values=True)

        self.assertEqual(reg_query["clickid"], ["{adv_click_id}"])
        self.assertEqual(reg_query["secure"], ["sec+ret&hash"])
        self.assertEqual(reg_query["goal"], ["1"])
        self.assertEqual(reg_query["status"], ["1"])
        self.assertEqual(dep_query["clickid"], ["{adv_click_id}"])
        self.assertEqual(dep_query["secure"], ["sec+ret&hash"])
        self.assertEqual(dep_query["goal"], ["dep&main"])
        self.assertEqual(dep_query["status"], ["2"])


if __name__ == "__main__":
    unittest.main()
