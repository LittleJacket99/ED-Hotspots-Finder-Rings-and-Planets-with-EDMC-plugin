import unittest
from unittest.mock import patch
import community_deposits as finder
from edmc_plugin.EDHF_Community_Navigator import community_api as edmc
from edmc_plugin.EDHF_Community_Navigator.pagination import collect_pages


class Response:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status
    def json(self):
        return self.payload


class PaginationTests(unittest.TestCase):
    def test_both_clients_follow_cursors_with_same_filter_and_credential(self):
        for module, credential in [(finder, "_read_api_key"), (edmc, "get_api_key")]:
            with self.subTest(client=module.__name__), patch.object(module, credential, return_value="synthetic"), \
                    patch.object(module.requests, "get", side_effect=[
                        Response({"status": "ok", "deposits": [], "next_cursor": "page2"}),
                        Response({"status": "ok", "deposits": [], "next_cursor": None})]) as get:
                if module is finder:
                    finder.fetch_all_deposits(commander="Test")
                else:
                    edmc.fetch_system_deposits("Sol", commander="Test")
                self.assertEqual(get.call_count, 2)
                self.assertEqual(get.call_args_list[1].kwargs["params"]["cursor"], "page2")
                for call in get.call_args_list:
                    self.assertEqual(call.kwargs["headers"]["Authorization"], "Bearer synthetic")
                    if module is edmc:
                        self.assertEqual(call.kwargs["params"]["system"], "Sol")

    def test_repeated_cursor_and_rate_limit_stop_without_retry_or_partial_result(self):
        for module, credential in [(finder, "_read_api_key"), (edmc, "get_api_key")]:
            for responses in [[Response({"deposits": [], "next_cursor": "repeat"})] * 2,
                              [Response({"deposits": [], "next_cursor": "next"}), Response({}, 429)]]:
                with self.subTest(client=module.__name__), patch.object(module, credential, return_value="synthetic"), \
                        patch.object(module.requests, "get", side_effect=responses) as get:
                    error = finder.CommunityDepositsError if module is finder else edmc.CommunityAPIError
                    with self.assertRaises(error):
                        if module is finder:
                            finder.fetch_all_deposits(commander="Test")
                        else:
                            edmc.fetch_system_deposits("Sol", commander="Test")
                    self.assertEqual(get.call_count, 2)

    def test_complete_pages_no_lost_or_duplicate_records(self):
        pages = iter([([{"id": i} for i in range(500)], "second"), ([{"id": 500}], None)])
        result = collect_pages(lambda _: next(pages), {}, RuntimeError)
        self.assertEqual([r["id"] for r in result], list(range(501)))
