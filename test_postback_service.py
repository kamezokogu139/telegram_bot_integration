import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import postback_service


class FakeResponse:
    status_code = 200

    def json(self):
        return {"status": 1}


class CapturingClient:
    requested_url = None

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url):
        CapturingClient.requested_url = url
        return FakeResponse()


class SendPostbackTests(unittest.TestCase):
    def test_send_postback_url_encodes_dynamic_query_values(self):
        with patch.object(postback_service.httpx, "Client", CapturingClient):
            success, _ = postback_service.send_postback(
                clickid="click/123",
                secure="sec+ret",
                goal="ftd&bonus=1",
                status=2,
                pid="partner 108",
            )

        self.assertTrue(success)
        parsed = urlparse(CapturingClient.requested_url)
        query = parse_qs(parsed.query)

        self.assertEqual(query["clickid"], ["click/123"])
        self.assertEqual(query["secure"], ["sec+ret"])
        self.assertEqual(query["goal"], ["ftd&bonus=1"])
        self.assertEqual(query["action_id"], ["TEST_partner 108"])
        self.assertNotIn("bonus", query)


if __name__ == "__main__":
    unittest.main()
