#!/usr/bin/env python3
"""Read-only, dependency-free client for Photolike's public reference."""

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ORIGIN = "https://photolike-nine.vercel.app"
PREFIX = "/api/resources/v1"
TIMEOUT_SECONDS = 12
MAX_RESPONSE_BYTES = 1024 * 1024
ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,99}\Z")


class PhotolikeError(Exception):
    """A bounded public-service or validation failure."""


def checked_id(value):
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise PhotolikeError("Choose an exact supported ID from the catalog.")
    return value


def allowed_url(url):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc != "photolike-nine.vercel.app"
            or parsed.fragment):
        return False
    if parsed.path == PREFIX:
        return not parsed.query
    if parsed.path == PREFIX + "/kit":
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        return (set(query) == {"bodyId", "lensId"}
                and all(len(values) == 1 and ID_PATTERN.fullmatch(values[0])
                        for values in query.values()))
    if parsed.path.startswith(PREFIX + "/recipes/"):
        return (not parsed.query and bool(ID_PATTERN.fullmatch(
            parsed.path[len(PREFIX + "/recipes/"):])) )
    return False


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise PhotolikeError("Photolike redirected the request; no redirect was followed.")


def fetch_json(url, headers):
    """No cookies, credentials, redirects, body, uploads, or configurable host."""
    if not allowed_url(url):
        raise PhotolikeError("Only documented Photolike HTTPS GET resources are allowed.")
    request = urllib.request.Request(url, headers=headers, method="GET")
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise PhotolikeError("Photolike did not return a successful resource.")
            content_type = response.headers.get_content_type()
            if content_type != "application/json":
                raise PhotolikeError("Photolike returned a non-JSON response.")
            data = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as error:
        raise PhotolikeError("Photolike returned HTTP {}.".format(error.code)) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise PhotolikeError("Photolike could not be reached within the request limit.") from None
    if len(data) > MAX_RESPONSE_BYTES:
        raise PhotolikeError("Photolike's response exceeded the JSON size limit.")
    try:
        result = json.loads(data.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError):
        raise PhotolikeError("Photolike returned invalid JSON.") from None
    if not isinstance(result, dict):
        raise PhotolikeError("Photolike returned an unexpected resource shape.")
    return result


def source_url(value):
    if not isinstance(value, str):
        raise PhotolikeError("The resource is missing a usable source URL.")
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise PhotolikeError("The resource is missing a usable HTTPS source URL.")
    return value


class Client:
    def __init__(self, test=False, fetcher=None):
        self.fetcher = fetcher or fetch_json
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "photolike-agent-skill/1.0",
            "X-Photolike-Agent": "1",
            "X-Photolike-Channel": "photolike-skill",
        }
        if test:
            self.headers["X-Photolike-Test"] = "1"

    def _get(self, path):
        url = ORIGIN + path
        if not allowed_url(url):
            raise PhotolikeError("Unsupported resource request.")
        result = self.fetcher(url, dict(self.headers))
        if not isinstance(result, dict):
            raise PhotolikeError("Photolike returned an unexpected resource shape.")
        return result

    def catalog(self):
        result = self._get(PREFIX)
        if not all(isinstance(result.get(key), list) for key in ("bodies", "lenses", "recipes")):
            raise PhotolikeError("Photolike returned an incomplete catalog.")
        return result

    def kit(self, body_id, lens_id):
        query = urllib.parse.urlencode({"bodyId": checked_id(body_id), "lensId": checked_id(lens_id)})
        result = self._get(PREFIX + "/kit?" + query)
        if (result.get("bodyId") != body_id or result.get("lensId") != lens_id
                or type(result.get("compatible")) is not bool):
            raise PhotolikeError("Photolike returned an invalid kit check.")
        return result

    def recipe(self, recipe_id):
        recipe_id = checked_id(recipe_id)
        result = self._get(PREFIX + "/recipes/" + recipe_id)
        if result.get("id") != recipe_id:
            raise PhotolikeError("Photolike returned a different or missing recipe.")
        return result

    def brief(self, recipe_id):
        recipe = self.recipe(recipe_id)
        kit = self.kit(recipe.get("bodyId"), recipe.get("lensId"))
        if not kit["compatible"]:
            raise PhotolikeError("The recipe's native kit is incompatible; no brief was produced.")
        practice = recipe.get("fieldPractice")
        if not isinstance(practice, dict) or not all(
                isinstance(practice.get(key), str) and practice[key].strip()
                for key in ("purpose", "try", "inspect", "watchFor", "source")):
            raise PhotolikeError("This recipe has no complete practical exercise; no brief was produced.")
        return {
            "recipeId": recipe["id"],
            "creativeLook": {key: recipe.get(key) for key in
                             ("name", "title", "description", "aperture", "tonalNotes")},
            "nativeKit": kit,
            "fieldPractice": practice,
            "sources": {
                "recipe": source_url(recipe.get("citation")),
                "manufacturer": source_url(kit.get("source")),
                "specificationsCheckedAt": kit.get("checkedAt"),
                "teaching": source_url(practice.get("source")),
                "editorialReviewDate": practice.get("reviewedAt"),
                "sourcePublicationDate": practice.get("sourcePublicationDate"),
            },
            "visit": recipe.get("visit"),
            "limitations": [
                "A practical exercise for a future real photograph, not a metered exposure prescription.",
                "The creative look and its kit aperture are separate from this exercise.",
                "Use settings supported by the actual lens; adapt to available light, motion and intent.",
                "No images were uploaded, generated or edited; no account access was granted.",
                "Preserve people, appearance, clothing and real scene; imagined views cannot verify hidden detail.",
            ],
        }


def main(argv=None, fetcher=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", action="store_true", help="Mark internal QA/demo requests.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("catalog", "kit", "recipe", "brief"):
        command = commands.add_parser(name)
        command.add_argument("--test", action="store_true", default=argparse.SUPPRESS)
        if name == "kit":
            command.add_argument("body_id")
            command.add_argument("lens_id")
        elif name in ("recipe", "brief"):
            command.add_argument("recipe_id")
    args = parser.parse_args(argv)
    client = Client(test=args.test, fetcher=fetcher)
    try:
        if args.command == "kit":
            result = client.kit(args.body_id, args.lens_id)
        elif args.command == "catalog":
            result = client.catalog()
        else:
            result = getattr(client, args.command)(args.recipe_id)
    except PhotolikeError as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
