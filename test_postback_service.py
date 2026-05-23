import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import postback_service


class _FakeResponse:
    status_code = 200

    def json(self):
        return {"status": 1}


class _FakeClient:
    requested_url = None

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url):
        type(self).requested_url = url
        return _FakeResponse()


class SendPostbackTests(unittest.TestCase):
    def test_send_postback_url_encodes_dynamic_query_values(self):
        with patch.object(postback_service.httpx, "Client", _FakeClient):
            success, _ = postback_service.send_postback(
                clickid="clk&id=1",
                secure="sec&ret=2",
                goal="dep&osit tier=1",
                status=2,
                pid="42&bad=1",
            )

        self.assertTrue(success)
        parsed = urlparse(_FakeClient.requested_url)
        params = parse_qs(parsed.query)

        self.assertEqual(params["clickid"], ["clk&id=1"])
        self.assertEqual(params["secure"], ["sec&ret=2"])
        self.assertEqual(params["goal"], ["dep&osit tier=1"])
        self.assertEqual(params["status"], ["2"])
        self.assertEqual(params["action_id"], ["TEST_42&bad=1"])
        self.assertNotIn("ret", params)
        self.assertNotIn("bad", params)


if __name__ == "__main__":
    unittest.main()
