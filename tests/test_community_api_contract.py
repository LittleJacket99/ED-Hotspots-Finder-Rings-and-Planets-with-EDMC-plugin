import unittest
from unittest.mock import Mock, patch

import requests

import community_deposits
import rhinospotter_sync
from edmc_plugin.EDHF_Community_Navigator import community_api
from edmc_plugin.EDHF_Community_Navigator.batch_protocol import (
    BatchProtocolError,
    validate_batch_request,
    validate_batch_response,
)


class Response:
    status_code = 200
    text = ""

    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error

    def json(self):
        if self.error:
            raise self.error
        return self.payload


class BatchProtocolTests(unittest.TestCase):
    def test_outgoing_batch_ids_must_be_valid_and_unique_before_send(self):
        for sent in (
            [{"report_id": "a"}, {"report_id": "a"}],
            [{"report_id": ""}],
            [{"report_id": " padded "}],
            [{"report_id": 17}],
            [None],
        ):
            with self.subTest(sent=sent), self.assertRaises(BatchProtocolError):
                validate_batch_request(sent)

    def test_maps_unordered_results_and_keeps_item_failure_retryable(self):
        sent = [{"report_id": "a"}, {"report_id": "b"}]
        payload = {
            "status": "ok", "received": 2,
            "results": [
                {"ok": False, "report_id": "b", "error": "retry"},
                {"ok": True, "report_id": "a", "action": "inserted"},
            ],
        }
        result = validate_batch_response(sent, payload)
        self.assertFalse(result["b"]["ok"])
        self.assertEqual(result["a"]["action"], "inserted")

    def test_accepts_batch_limit_and_rejects_over_limit_by_chunking(self):
        self.assertEqual(len(list(community_api.chunks([{}] * 200))), 1)
        self.assertEqual([len(x) for x in community_api.chunks([{}] * 201)], [200, 1])
        self.assertEqual([len(x) for x in rhinospotter_sync.chunks([{}] * 201, 200)], [200, 1])

    def test_invalid_top_level_response_shapes_are_rejected(self):
        sent = [{"report_id": "a"}]
        for payload in (
            None,
            {"status": "error", "received": 1, "results": [{}]},
            {"status": "ok", "received": 0, "results": [{}]},
            {"status": "ok", "received": True, "results": [{}]},
            {"status": "ok", "received": 1.0, "results": [{}]},
            {"status": "ok", "received": 1},
            {"status": "ok", "received": 1, "results": {}},
            {"status": "ok", "received": 1, "results": []},
        ):
            with self.subTest(payload=payload), self.assertRaises(BatchProtocolError):
                validate_batch_response(sent, payload)

    def test_report_id_bijection_and_result_types_are_enforced(self):
        sent = [{"report_id": "a"}, {"report_id": "b"}]
        bad_items = [
            [{"ok": True, "action": "inserted"}, {"ok": True, "report_id": "b", "action": "inserted"}],
            [{"ok": True, "report_id": "x", "action": "inserted"}, {"ok": True, "report_id": "b", "action": "inserted"}],
            [{"ok": True, "report_id": "a", "action": "inserted"}, {"ok": True, "report_id": "a", "action": "inserted"}],
            [{"ok": "true", "report_id": "a", "action": "inserted"}, {"ok": True, "report_id": "b", "action": "inserted"}],
            [{"ok": True, "report_id": "a", "action": "unknown"}, {"ok": True, "report_id": "b", "action": "inserted"}],
        ]
        for items in bad_items:
            with self.subTest(items=items), self.assertRaises(BatchProtocolError):
                validate_batch_response(sent, {"status": "ok", "received": 2, "results": items})

    def test_duplicate_or_missing_sent_ids_are_rejected(self):
        for sent in ([{"report_id": "a"}, {"report_id": "a"}], [{"report_id": ""}]):
            with self.subTest(sent=sent), self.assertRaises(BatchProtocolError):
                validate_batch_response(sent, {"status": "ok", "received": len(sent), "results": []})


class RequestAuthenticationTests(unittest.TestCase):
    def test_desktop_read_sends_bearer_and_no_secret_in_result(self):
        response = Response({"status": "ok", "deposits": []})
        with patch.object(community_deposits, "_read_api_key", return_value="edcd_fixture"), \
                patch.object(community_deposits.requests, "get", return_value=response) as get:
            community_deposits.fetch_all_deposits(commander="CMDR")
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer edcd_fixture")

    def test_desktop_read_and_batch_use_the_same_credential(self):
        read_response = Response({"status": "ok", "deposits": []})
        with patch.object(community_deposits, "get_api_key", return_value="edcd_fixture") as read_key, \
                patch.object(community_deposits.requests, "get", return_value=read_response) as get:
            community_deposits.fetch_all_deposits(commander="CMDR")

        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"status":"ok","received":1,"results":[]}'
        with patch.object(rhinospotter_sync, "get_api_key", return_value="edcd_fixture") as write_key, \
                patch.object(rhinospotter_sync.urllib.request, "urlopen", return_value=response) as post:
            rhinospotter_sync.send_batch([{"report_id": "r", "commander": "CMDR"}])

        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer edcd_fixture")
        self.assertEqual(post.call_args.args[0].get_header("Authorization"), "Bearer edcd_fixture")
        read_key.assert_called_once_with("CMDR")
        write_key.assert_called_once_with("CMDR")

    def test_plugin_read_sends_bearer(self):
        response = Response({"status": "ok", "deposits": []})
        with patch.object(community_api, "get_api_key", return_value="edcd_fixture") as credential, \
                patch.object(community_api.requests, "get", return_value=response) as get:
            community_api.fetch_system_deposits("Sol", commander="CMDR")
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer edcd_fixture")
        credential.assert_called_once_with("CMDR")

    def test_plugin_batch_sends_bearer_and_contract_body(self):
        response = Response({"status": "ok", "received": 1, "results": []})
        with patch.object(community_api, "get_api_key", return_value="edcd_fixture") as credential, \
                patch.object(community_api.requests, "post", return_value=response) as post:
            community_api.send_deposit_batch([{"report_id": "r", "commander": "CMDR"}])
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer edcd_fixture")
        self.assertEqual(post.call_args.kwargs["json"], {"deposits": [{"report_id": "r", "commander": "CMDR"}]})
        credential.assert_called_once_with("CMDR")

    def test_read_and_batch_use_same_shared_credential_accessor(self):
        import community_deposits
        from edmc_plugin.EDHF_Community_Navigator import api_credentials
        from edmc_plugin.EDHF_Community_Navigator import rhinospotter_client

        self.assertIs(community_deposits.get_api_key, api_credentials.get_api_key)
        self.assertIs(community_api.get_api_key, api_credentials.get_api_key)
        self.assertIs(rhinospotter_client.get_api_key, api_credentials.get_api_key)
        self.assertIs(rhinospotter_sync.get_api_key, api_credentials.get_api_key)

    def test_desktop_batch_sends_bearer_without_echoing_it_on_http_error(self):
        import io
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"status":"ok"}'
        with patch.object(rhinospotter_sync.urllib.request, "urlopen", return_value=response) as open_url:
            result = rhinospotter_sync.send_batch(
                [{"report_id": "r", "commander": "CMDR"}], api_key="edcd_fixture"
            )
        request = open_url.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer edcd_fixture")
        self.assertEqual(result, {"status": "ok"})
        http_error = rhinospotter_sync.urllib.error.HTTPError(
            "https://example.invalid", 403, "forbidden", {}, io.BytesIO(b"edcd_fixture")
        )
        with patch.object(rhinospotter_sync.urllib.request, "urlopen", side_effect=http_error):
            with self.assertRaises(RuntimeError) as caught:
                rhinospotter_sync.send_batch(
                    [{"report_id": "r", "commander": "CMDR"}], api_key="edcd_fixture"
                )
            self.assertNotIn("edcd_fixture", str(caught.exception))

    def test_desktop_batch_network_and_malformed_json_errors_do_not_echo_key(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"echo":"edcd_fixture"'
        with patch.object(rhinospotter_sync.urllib.request, "urlopen", return_value=response):
            with self.assertRaises(ValueError) as caught:
                rhinospotter_sync.send_batch(
                    [{"report_id": "r", "commander": "CMDR"}], api_key="edcd_fixture"
                )
            self.assertNotIn("edcd_fixture", str(caught.exception))
        with patch.object(
            rhinospotter_sync.urllib.request,
            "urlopen",
            side_effect=rhinospotter_sync.urllib.error.URLError("edcd_fixture"),
        ):
            with self.assertRaises(RuntimeError) as caught:
                rhinospotter_sync.send_batch(
                    [{"report_id": "r", "commander": "CMDR"}], api_key="edcd_fixture"
                )
            self.assertNotIn("edcd_fixture", str(caught.exception))

    def test_http_network_and_json_errors_do_not_echo_key(self):
        with patch.object(community_api, "get_api_key", return_value="edcd_fixture"), \
                patch.object(community_api.requests, "get", return_value=Response({}, error=ValueError())):
            with self.assertRaises(community_api.CommunityAPIError) as caught:
                community_api.fetch_system_deposits("Sol", commander="CMDR")
            self.assertNotIn("edcd_fixture", str(caught.exception))
        with patch.object(community_api, "get_api_key", return_value="edcd_fixture"), \
                patch.object(community_api.requests, "get", side_effect=requests.ConnectionError("edcd_fixture")):
            with self.assertRaises(community_api.CommunityAPIError) as caught:
                community_api.fetch_system_deposits("Sol", commander="CMDR")
            self.assertNotIn("edcd_fixture", str(caught.exception))
        response = Response({})
        response.status_code = 403
        response.text = "Bearer edcd_fixture"
        with patch.object(community_api, "get_api_key", return_value="edcd_fixture"), \
                patch.object(community_api.requests, "get", return_value=response):
            with self.assertRaises(community_api.CommunityAPIError) as caught:
                community_api.fetch_system_deposits("Sol", commander="CMDR")
            self.assertNotIn("edcd_fixture", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
