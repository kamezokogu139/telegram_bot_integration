import unittest
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
    def test_send_postback_encodes_dynamic_query_values(self):
        with patch.object(postback_service.httpx, "Client", _FakeClient):
            success, _ = postback_service.send_postback(
                "click&123",
                "sec=ret",
                "first deposit&bonus=1",
                2,
                "pid/42",
            )

        self.assertTrue(success)
        self.assertEqual(
            _FakeClient.requested_url,
            (
                "https://offers.x-partners.com/postback"
                "?clickid=click%26123"
                "&secure=sec%3Dret"
                "&goal=first+deposit%26bonus%3D1"
                "&status=2"
                "&action_id=TEST_pid%2F42"
            ),
        )


if __name__ == "__main__":
    unittest.main()
