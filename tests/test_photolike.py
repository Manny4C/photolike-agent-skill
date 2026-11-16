import contextlib
import copy
import importlib.util
import io
import json
from email.message import Message
from pathlib import Path
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "skills/photolike-photography/scripts/photolike.py"
spec = importlib.util.spec_from_file_location("photolike", SCRIPT)
photolike = importlib.util.module_from_spec(spec)
spec.loader.exec_module(photolike)

RECIPE = {
    "id": "sony", "name": "Modern Precision", "bodyId": "sony-a7r-v",
    "lensId": "sony-fe-50", "aperture": "f/1.2", "tonalNotes": ["Clean color"],
    "citation": photolike.ORIGIN + "/api/resources/v1/recipes/sony",
    "visit": photolike.ORIGIN + "/api/resources/v1/visit",
    "fieldPractice": {"purpose": "Future real photograph", "try": "Compare f/8 and f/11 if supported.",
                      "inspect": "Check near and far detail.", "watchFor": "Check motion and exposure.",
                      "source": "https://www.nikonusa.com/teaching", "reviewedAt": "2026-11-16",
                      "sourcePublicationDate": None},
}
KIT = {"compatible": True, "bodyId": "sony-a7r-v", "lensId": "sony-fe-50",
       "source": "https://electronics.sony.com/manufacturer", "checkedAt": "2026-10-25"}


class StubFetch:
    def __init__(self, recipe=None, kit=None):
        self.calls = []
        self.recipe = copy.deepcopy(RECIPE if recipe is None else recipe)
        self.kit = copy.deepcopy(KIT if kit is None else kit)

    def __call__(self, url, headers):
        self.calls.append((url, headers))
        if url == photolike.ORIGIN + photolike.PREFIX:
            return {"bodies": [], "lenses": [], "recipes": []}
        if "/recipes/" in url:
            return copy.deepcopy(self.recipe)
        return copy.deepcopy(self.kit)


class ClientTests(unittest.TestCase):
    def test_brief_checks_native_kit_preserves_aperture_and_real_source_dates(self):
        fetch = StubFetch()
        result = photolike.Client(test=True, fetcher=fetch).brief("sony")
        self.assertEqual(len(fetch.calls), 2)
        self.assertTrue(fetch.calls[1][0].endswith("/kit?bodyId=sony-a7r-v&lensId=sony-fe-50"))
        self.assertEqual(result["creativeLook"]["aperture"], "f/1.2")
        self.assertIn("f/8", result["fieldPractice"]["try"])
        self.assertIsNone(result["sources"]["sourcePublicationDate"])
        self.assertEqual(result["sources"]["editorialReviewDate"], "2026-11-16")
        for url, headers in fetch.calls:
            self.assertTrue(photolike.allowed_url(url))
            self.assertEqual(headers["X-Photolike-Agent"], "1")
            self.assertEqual(headers["X-Photolike-Channel"], "photolike-skill")
            self.assertEqual(headers["X-Photolike-Test"], "1")
            self.assertFalse({"Cookie", "Authorization", "X-Render-Key"} & set(headers))

    def test_catalog_and_recipe_return_reference_data_without_extra_requests(self):
        fetch = StubFetch()
        client = photolike.Client(fetcher=fetch)
        self.assertEqual(client.catalog(), {"bodies": [], "lenses": [], "recipes": []})
        self.assertEqual(client.recipe("sony")["id"], "sony")
        self.assertEqual(len(fetch.calls), 2)
        self.assertNotIn("X-Photolike-Test", fetch.calls[0][1])

    def test_incompatible_kit_can_be_reported_but_cannot_produce_brief(self):
        kit = dict(KIT, compatible=False)
        client = photolike.Client(fetcher=StubFetch(kit=kit))
        self.assertFalse(client.kit("sony-a7r-v", "sony-fe-50")["compatible"])
        with self.assertRaisesRegex(photolike.PhotolikeError, "incompatible"):
            client.brief("sony")

    def test_wrong_ids_truthy_compatibility_missing_practice_or_sources_fail(self):
        for kit in (dict(KIT, compatible="true"), dict(KIT, bodyId="another-body")):
            with self.assertRaises(photolike.PhotolikeError):
                photolike.Client(fetcher=StubFetch(kit=kit)).brief("sony")
        for recipe in (dict(RECIPE, id="other"), dict(RECIPE, fieldPractice=None), dict(RECIPE, citation=None)):
            with self.assertRaises(photolike.PhotolikeError):
                photolike.Client(fetcher=StubFetch(recipe=recipe)).brief("sony")

    def test_invalid_input_does_not_make_a_request(self):
        fetch = StubFetch()
        client = photolike.Client(fetcher=fetch)
        for value in ("https://evil.example", "../sony", "sony?prompt=private", "my photo", "x" * 101):
            with self.assertRaises(photolike.PhotolikeError):
                client.recipe(value)
        self.assertEqual(fetch.calls, [])

    def test_fixed_origin_and_route_allowlist(self):
        for url in ("http://photolike-nine.vercel.app/api/resources/v1", "https://evil.example/api/resources/v1",
                    "https://photolike-nine.vercel.app.evil.example/api/resources/v1",
                    photolike.ORIGIN + "/api/render", photolike.ORIGIN + "/api/resources/v1/visit",
                    photolike.ORIGIN + "/api/resources/v1?prompt=private"):
            self.assertFalse(photolike.allowed_url(url))
            with self.assertRaises(photolike.PhotolikeError):
                photolike.fetch_json(url, {})

    def test_redirects_are_not_followed(self):
        with self.assertRaisesRegex(photolike.PhotolikeError, "redirect"):
            photolike.NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://evil.example")

    def test_http_fetch_has_timeout_size_and_json_checks_without_network(self):
        headers = Message(); headers["Content-Type"] = "application/json"
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.status = 200; response.headers = headers
        response.read.return_value = b'{"version":1}'
        opener = mock.Mock(); opener.open.return_value = response
        with mock.patch.object(photolike.urllib.request, "build_opener", return_value=opener):
            self.assertEqual(photolike.fetch_json(photolike.ORIGIN + photolike.PREFIX, {}), {"version": 1})
            self.assertEqual(opener.open.call_args.kwargs["timeout"], photolike.TIMEOUT_SECONDS)
            self.assertEqual(opener.open.call_args.args[0].get_method(), "GET")
            self.assertIsNone(opener.open.call_args.args[0].data)
            response.read.assert_called_with(photolike.MAX_RESPONSE_BYTES + 1)
            for payload in (b"[]", b"not-json", b"x" * (photolike.MAX_RESPONSE_BYTES + 1)):
                response.read.return_value = payload
                with self.assertRaises(photolike.PhotolikeError):
                    photolike.fetch_json(photolike.ORIGIN + photolike.PREFIX, {})
            response.read.side_effect = TimeoutError()
            with self.assertRaisesRegex(photolike.PhotolikeError, "limit"):
                photolike.fetch_json(photolike.ORIGIN + photolike.PREFIX, {})

    def test_cli_test_flag_before_or_after_command_and_nonzero_failure(self):
        for argv in (["--test", "brief", "sony"], ["brief", "sony", "--test"]):
            fetch = StubFetch(); out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(photolike.main(argv, fetcher=fetch), 0)
            self.assertEqual(json.loads(out.getvalue())["recipeId"], "sony")
            self.assertTrue(all(headers["X-Photolike-Test"] == "1" for _, headers in fetch.calls))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(photolike.main(["brief", "sony", "--test"], fetcher=StubFetch(kit=dict(KIT, compatible=False))), 1)
        self.assertIn("incompatible", json.loads(err.getvalue())["error"])


if __name__ == "__main__":
    unittest.main()
