import unittest
from unittest.mock import patch

import httpx

from postback_service import (
    _is_tracker_url,
    extract_clickid_from_redirect,
    extract_offer_id_from_url,
    extract_pid_from_url,
)


class TrackerDomainValidationTests(unittest.TestCase):
    def test_tracker_domain_must_be_actual_hostname(self):
        spoofed = "https://evil.example/4837?pid=108&next=https://trk.xplink/click"

        self.assertFalse(_is_tracker_url(spoofed))
        self.assertIsNone(extract_offer_id_from_url(spoofed))
        self.assertIsNone(extract_pid_from_url(spoofed))

    def test_tracker_domain_allows_exact_host_and_subdomain(self):
        self.assertTrue(_is_tracker_url("https://trk.xplink/click?offer_id=4837&pid=108"))
        self.assertTrue(_is_tracker_url("https://123.trk.xplink/click?pid=108"))
        self.assertEqual(extract_offer_id_from_url("https://123.trk.xplink/click?pid=108"), "123")
        self.assertEqual(extract_pid_from_url("https://trk.xplink/click?offer_id=4837&pid=108"), "108")

    def test_redirect_chain_does_not_trust_spoofed_tracker_url(self):
        responses = [
            httpx.Response(
                302,
                headers={
                    "Location": "https://evil.example/4837?pid=108&next=https://trk.xplink/click",
                },
                request=httpx.Request("GET", "https://affiliate.example/start"),
            ),
            httpx.Response(
                302,
                headers={"Location": "https://landing.example/?clickid=abc12345"},
                request=httpx.Request(
                    "GET",
                    "https://evil.example/4837?pid=108&next=https://trk.xplink/click",
                ),
            ),
            httpx.Response(
                200,
                request=httpx.Request("GET", "https://landing.example/?clickid=abc12345"),
            ),
        ]

        with patch("postback_service.httpx.Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            client.get.side_effect = responses

            clickid, offer_id, pid, error = extract_clickid_from_redirect("https://affiliate.example/start")

        self.assertIsNone(clickid)
        self.assertIsNone(offer_id)
        self.assertIsNone(pid)
        self.assertIn("ClickID не найден", error)


if __name__ == "__main__":
    unittest.main()
