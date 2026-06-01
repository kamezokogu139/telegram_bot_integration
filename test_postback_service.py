import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import postback_service


class _FakeResponse:
    status_code = 200

    def json(self):
        return {"status": 1}


class _CapturingClient:
    last_url = None

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url):
        type(self).last_url = url
        return _FakeResponse()


class SendPostbackTests(unittest.TestCase):
    def test_send_postback_url_encodes_dynamic_query_values(self):
        with patch.object(postback_service.httpx, "Client", _CapturingClient):
            success, _ = postback_service.send_postback(
                clickid="click&evil=1",
                secure="sec ret&sig=bad",
                goal="first deposit&extra=1",
                status=2,
                pid="pid 108",
            )

        self.assertTrue(success)
        parsed = urlparse(_CapturingClient.last_url)
        query = parse_qs(parsed.query)
        self.assertEqual(query["clickid"], ["click&evil=1"])
        self.assertEqual(query["secure"], ["sec ret&sig=bad"])
        self.assertEqual(query["goal"], ["first deposit&extra=1"])
        self.assertEqual(query["status"], ["2"])
        self.assertEqual(query["action_id"], ["TEST_pid 108"])
        self.assertNotIn("evil", query)
        self.assertNotIn("sig", query)
        self.assertNotIn("extra", query)


if __name__ == "__main__":
    unittest.main()
