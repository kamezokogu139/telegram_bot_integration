import unittest
from unittest.mock import patch

import httpx

from postback_service import _is_tracker_url, extract_clickid_from_redirect


class TrackerDomainValidationTest(unittest.TestCase):
    def test_accepts_configured_tracker_hosts_and_subdomains(self):
        self.assertTrue(_is_tracker_url("https://trk.xplink/click?offer_id=123&pid=108"))
        self.assertTrue(_is_tracker_url("https://123.trk.xplink/click?pid=108"))
        self.assertTrue(_is_tracker_url("https://foo.trk.goxp.tech/path"))

    def test_rejects_tracker_domain_outside_hostname(self):
        self.assertFalse(_is_tracker_url("https://evil.example/click?next=https://trk.xplink/123?pid=108"))
        self.assertFalse(_is_tracker_url("https://trk.xplink.evil.example/click?offer_id=123&pid=108"))
        self.assertFalse(_is_tracker_url("https://evil-trk.xplink.example/click?offer_id=123&pid=108"))

    def test_redirect_chain_does_not_trust_spoofed_tracker_url(self):
        responses = [
            httpx.Response(
                302,
                headers={
                    "Location": "https://evil.example/123?pid=108&next=https://trk.xplink/click",
                },
                request=httpx.Request("GET", "https://affiliate.example/start"),
            ),
            httpx.Response(
                302,
                headers={"Location": "https://landing.example/?clickid=abc12345"},
                request=httpx.Request(
                    "GET",
                    "https://evil.example/123?pid=108&next=https://trk.xplink/click",
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
