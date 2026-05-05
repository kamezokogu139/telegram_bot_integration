import unittest

from postback_service import _is_tracker_url, extract_offer_id_from_url, extract_pid_from_url


class TrackerDomainValidationTests(unittest.TestCase):
    def test_tracker_domain_must_be_hostname_not_query_substring(self):
        url = "https://evil.example/4837?next=https://trk.xplink/click&pid=108"

        self.assertFalse(_is_tracker_url(url))
        self.assertIsNone(extract_offer_id_from_url(url))
        self.assertIsNone(extract_pid_from_url(url))

    def test_tracker_domain_rejects_malformed_urls(self):
        self.assertFalse(_is_tracker_url("http://[::1"))

    def test_tracker_domain_allows_exact_host_and_subdomain(self):
        self.assertTrue(_is_tracker_url("https://trk.xplink/click?offer_id=4837&pid=108"))
        self.assertTrue(_is_tracker_url("https://123.trk.xplink/click?pid=108"))
        self.assertEqual(extract_offer_id_from_url("https://123.trk.xplink/click?pid=108"), "123")
        self.assertEqual(extract_pid_from_url("https://trk.xplink/click?offer_id=4837&pid=108"), "108")


if __name__ == "__main__":
    unittest.main()
