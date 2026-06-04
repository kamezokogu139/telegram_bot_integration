import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import postback_service


class _FakeResponse:
    status_code = 200

    def __init__(self, payload=None):
        self._payload = payload or {"status": 1}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class SendPostbackTests(unittest.TestCase):
    def test_send_postback_url_encodes_dynamic_query_values(self):
        requested_urls = []

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def get(self, url):
                requested_urls.append(url)
                return _FakeResponse()

        with patch.object(postback_service.httpx, "Client", FakeClient):
            success, _ = postback_service.send_postback(
                clickid="abc&spoofed=1",
                secure="sec ret&x=y",
                goal="dep&goal=registration",
                status=2,
                pid="108&action_id=evil",
            )

        self.assertTrue(success)
        query = parse_qs(urlparse(requested_urls[0]).query)
        self.assertEqual(query["clickid"], ["abc&spoofed=1"])
        self.assertEqual(query["secure"], ["sec ret&x=y"])
        self.assertEqual(query["goal"], ["dep&goal=registration"])
        self.assertEqual(query["status"], ["2"])
        self.assertEqual(query["action_id"], ["TEST_108&action_id=evil"])
        self.assertNotIn("spoofed", query)


class AdvertiserPostbackUrlTests(unittest.TestCase):
    def test_build_urls_uses_affise_payment_goals_and_statuses(self):
        payload = {
            "status": 1,
            "offer": {
                "hash_password": "secret",
                "payments": [
                    {"goal": 1, "title": "Registration"},
                    {"goal": "dep&special", "title": "Deposit"},
                ],
            },
        }

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def get(self, url, headers=None):
                return _FakeResponse(payload)

        with patch.object(postback_service.httpx, "Client", FakeClient):
            url_reg, url_dep, error = postback_service.build_postback_urls_for_advertiser("4837", pid="108")

        self.assertEqual(error, "")
        self.assertIn("clickid={adv_click_id}", url_reg)
        self.assertIn("clickid={adv_click_id}", url_dep)
        reg_query = parse_qs(urlparse(url_reg).query)
        dep_query = parse_qs(urlparse(url_dep).query)
        self.assertEqual(reg_query["clickid"], ["{adv_click_id}"])
        self.assertEqual(reg_query["secure"], ["secret"])
        self.assertEqual(reg_query["goal"], ["1"])
        self.assertEqual(reg_query["status"], ["1"])
        self.assertEqual(dep_query["goal"], ["dep&special"])
        self.assertEqual(dep_query["status"], ["2"])

    def test_build_urls_ignores_unknown_payment_goals_when_choosing_deposit(self):
        payload = {
            "status": 1,
            "offer": {
                "hash_password": "secret",
                "payments": [
                    {"goal": "lead", "title": "Lead"},
                    {"goal": "reg", "title": "Registration"},
                    {"goal": "dep", "title": "Deposit"},
                ],
            },
        }

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def get(self, url, headers=None):
                return _FakeResponse(payload)

        with patch.object(postback_service.httpx, "Client", FakeClient):
            url_reg, url_dep, error = postback_service.build_postback_urls_for_advertiser("4837")

        self.assertEqual(error, "")
        self.assertEqual(parse_qs(urlparse(url_reg).query)["goal"], ["reg"])
        self.assertEqual(parse_qs(urlparse(url_dep).query)["goal"], ["dep"])


if __name__ == "__main__":
    unittest.main()
