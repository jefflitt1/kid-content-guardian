import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import content_cache  # noqa: E402
import wikipedia_client  # noqa: E402


@pytest.fixture
def conn(tmp_path):
    return content_cache.connect(tmp_path / "test_cache.sqlite")


def make_client(conn, search_result, summary_result, search_calls=None, summary_calls=None):
    def search_fetch(title):
        if search_calls is not None:
            search_calls.append(title)
        return search_result

    def summary_fetch(page_title):
        if summary_calls is not None:
            summary_calls.append(page_title)
        return summary_result

    return wikipedia_client.WikipediaClient(conn, search_fetch=search_fetch, summary_fetch=summary_fetch)


def test_lookup_requires_no_api_key(conn):
    # Unlike the retired TMDB client, there's no credential gate at all here.
    client = make_client(conn, {"query": {"search": []}}, {})
    result = client.lookup("Some Show")
    assert result is not None  # succeeds with no key/env var configured


def test_lookup_happy_path(conn):
    search_calls, summary_calls = [], []
    search_result = {"query": {"search": [{"title": "Bluey (TV series)"}]}}
    summary_result = {
        "extract": "Bluey is an Australian animated series about a Blue Heeler puppy.",
        "description": "Australian animated television series",
        "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Bluey_(TV_series)"}},
    }
    client = make_client(conn, search_result, summary_result, search_calls, summary_calls)

    result = client.lookup("Bluey")

    assert result["page_title"] == "Bluey (TV series)"
    assert "Blue Heeler" in result["extract"]
    assert result["source_url"] == "https://en.wikipedia.org/wiki/Bluey_(TV_series)"
    assert search_calls == ["Bluey"]
    assert summary_calls == ["Bluey (TV series)"]


def test_lookup_caches_and_skips_second_fetch(conn):
    search_calls, summary_calls = [], []
    search_result = {"query": {"search": [{"title": "Bluey (TV series)"}]}}
    summary_result = {"extract": "calm show", "description": "kids show", "content_urls": {"desktop": {"page": "url"}}}
    client = make_client(conn, search_result, summary_result, search_calls, summary_calls)

    first = client.lookup("Bluey")
    second = client.lookup("Bluey")

    assert first == second
    assert search_calls == ["Bluey"]  # only fetched once
    assert summary_calls == ["Bluey (TV series)"]


def test_lookup_no_search_results_caches_empty_and_does_not_call_summary(conn):
    summary_calls = []
    client = make_client(conn, {"query": {"search": []}}, {}, summary_calls=summary_calls)

    result = client.lookup("Totally Made Up Title Xyzzy")

    assert result["page_title"] is None
    assert result["extract"] is None
    assert summary_calls == []  # never called -- nothing to summarize


def test_lookup_is_case_insensitive_on_repeat_calls(conn):
    search_calls = []
    search_result = {"query": {"search": [{"title": "Bluey (TV series)"}]}}
    summary_result = {"extract": "calm", "description": "d", "content_urls": {"desktop": {"page": "url"}}}
    client = make_client(conn, search_result, summary_result, search_calls)

    client.lookup("Bluey")
    client.lookup("BLUEY")
    client.lookup("  bluey  ")

    assert search_calls == ["Bluey"]  # normalized cache key hit on the later two calls
