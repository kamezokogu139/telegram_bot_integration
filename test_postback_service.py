import unittest
from urllib.parse import parse_qs, urlparse

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
    def test_send_postback_url_encodes_goal_with_query_separator(self):
        original_client = postback_service.httpx.Client
        try:
            postback_service.httpx.Client = _CapturingClient

            success, _ = postback_service.send_postback(
                clickid="abc12345",
                secure="secure-token",
                goal="ftd&bonus=1",
                status=2,
                pid="108",
            )
        finally:
            postback_service.httpx.Client = original_client

        self.assertTrue(success)
        parsed_params = parse_qs(urlparse(_CapturingClient.last_url).query)
        self.assertEqual(parsed_params["goal"], ["ftd&bonus=1"])
        self.assertNotIn("bonus", parsed_params)


if __name__ == "__main__":
    unittest.main()
