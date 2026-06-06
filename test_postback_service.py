import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import postback_service


class ParseOfferGoalsTests(unittest.TestCase):
    def test_numeric_registration_goal_keeps_registration_status(self):
        goals = postback_service._parse_offer_goals({
            "payments": [
                {"goal": 1, "title": "Registration payout"},
                {"goal": "dep&main", "title": "Deposit payout"},
            ],
        })

        self.assertEqual(
            [
                {"value": "1", "status": 1},
                {"value": "dep&main", "status": 2},
            ],
            [{"value": goal["value"], "status": goal["status"]} for goal in goals],
        )

    def test_deposit_goal_title_mentioning_registration_stays_deposit(self):
        self.assertEqual(
            2,
            postback_service.infer_goal_status("dep", "After registration deposit"),
        )


class _FakePostbackResponse:
    status_code = 200

    def json(self):
        return {"status": 1}


class _CapturingPostbackClient:
    last_url = None

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url):
        type(self).last_url = url
        return _FakePostbackResponse()


class _FakeOfferResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "status": 1,
            "offer": {
                "hash_password": "sec ret&sig=bad",
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


class _FakeOfferWithUnknownBeforeDepositResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "status": 1,
            "offer": {
                "hash_password": "secure",
                "payments": [
                    {"goal": "reg", "title": "Registration payout"},
                    {"goal": "kyc", "title": "KYC approved"},
                    {"goal": "ftd", "title": "First deposit"},
                ],
            },
        }


class _FakeOfferWithUnknownBeforeDepositClient(_FakeOfferClient):
    def get(self, url, *args, **kwargs):
        return _FakeOfferWithUnknownBeforeDepositResponse()


class _FakeOfferWithoutDepositResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "status": 1,
            "offer": {
                "hash_password": "secure",
                "payments": [
                    {"goal": "reg", "title": "Registration payout"},
                    {"goal": "kyc", "title": "KYC approved"},
                ],
            },
        }


class _FakeOfferWithoutDepositClient(_FakeOfferClient):
    def get(self, url, *args, **kwargs):
        return _FakeOfferWithoutDepositResponse()


class SendPostbackTests(unittest.TestCase):
    def test_send_postback_url_encodes_dynamic_query_values(self):
        with patch.object(postback_service.httpx, "Client", _CapturingPostbackClient):
            success, _ = postback_service.send_postback(
                clickid="click&evil=1",
                secure="sec ret&sig=bad",
                goal="first deposit&extra=1",
                status=2,
                pid="pid 108",
            )

        self.assertTrue(success)
        query = parse_qs(urlparse(_CapturingPostbackClient.last_url).query)
        self.assertEqual(query["clickid"], ["click&evil=1"])
        self.assertEqual(query["secure"], ["sec ret&sig=bad"])
        self.assertEqual(query["goal"], ["first deposit&extra=1"])
        self.assertEqual(query["status"], ["2"])
        self.assertEqual(query["action_id"], ["TEST_pid 108"])
        self.assertNotIn("evil", query)
        self.assertNotIn("sig", query)
        self.assertNotIn("extra", query)


class BuildAdvertiserPostbackUrlTests(unittest.TestCase):
    def test_build_postback_urls_use_offer_payment_goals_and_encode_values(self):
        with patch.object(postback_service.httpx, "Client", _FakeOfferClient):
            url_reg, url_dep, error = postback_service.build_postback_urls_for_advertiser("4837")

        self.assertEqual(error, "")

        reg_query = parse_qs(urlparse(url_reg).query)
        dep_query = parse_qs(urlparse(url_dep).query)
        self.assertEqual(reg_query["clickid"], ["{adv_click_id}"])
        self.assertEqual(reg_query["secure"], ["sec ret&sig=bad"])
        self.assertEqual(reg_query["goal"], ["1"])
        self.assertEqual(reg_query["status"], ["1"])
        self.assertEqual(dep_query["clickid"], ["{adv_click_id}"])
        self.assertEqual(dep_query["secure"], ["sec ret&sig=bad"])
        self.assertEqual(dep_query["goal"], ["dep&main"])
        self.assertEqual(dep_query["status"], ["2"])
        self.assertNotIn("sig", reg_query)
        self.assertNotIn("sig", dep_query)

    def test_build_postback_urls_do_not_use_unknown_goal_as_deposit(self):
        with patch.object(postback_service.httpx, "Client", _FakeOfferWithUnknownBeforeDepositClient):
            _, url_dep, error = postback_service.build_postback_urls_for_advertiser("4837")

        self.assertEqual(error, "")
        self.assertEqual(parse_qs(urlparse(url_dep).query)["goal"], ["ftd"])

    def test_build_postback_urls_fail_when_explicit_deposit_goal_missing(self):
        with patch.object(postback_service.httpx, "Client", _FakeOfferWithoutDepositClient):
            url_reg, url_dep, error = postback_service.build_postback_urls_for_advertiser("4837")

        self.assertIsNone(url_reg)
        self.assertIsNone(url_dep)
        self.assertEqual(error, "В оффере не найдены цели регистрации и депозита")


if __name__ == "__main__":
    unittest.main()
