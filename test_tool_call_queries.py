"""Unit test for pipeline._tool_call_queries — the web_search argument parser.

Pure-function test, no network/token needed. The function must pull queries out
of both the normal {"query": "..."} shape AND GPT-4o's multi_tool_use.parallel
wrapper, which nests several parallel calls and has no top-level "query" — the
bug this branch fixes (the search used to silently run on an empty string).

Usage: .venv/bin/python test_tool_call_queries.py
"""
import json

from agent.pipeline import _tool_call_queries as q

CASES = [
    # (label, arguments, expected)
    ("normal single query", json.dumps({"query": "free AZ-900 guide"}),
     ["free AZ-900 guide"]),
    ("query is trimmed", json.dumps({"query": "  spaced  "}), ["spaced"]),
    ("multi_tool_use.parallel wrapper", json.dumps({"tool_uses": [
        {"recipient_name": "functions.web_search", "parameters": {"query": "one"}},
        {"recipient_name": "functions.web_search", "parameters": {"query": "two"}},
    ]}), ["one", "two"]),
    ("wrapper using 'arguments' key", json.dumps({"tool_uses": [
        {"arguments": {"query": "alt"}},
    ]}), ["alt"]),
    ("wrapper skips empty/blank/non-dict/missing-query entries",
     json.dumps({"tool_uses": [
         {"parameters": {"query": "keep"}},
         {"parameters": {"query": "   "}},
         {"parameters": {"query": ""}},
         {"parameters": {}},
         "not-a-dict",
         {"parameters": {"query": 7}},
     ]}), ["keep"]),
    ("empty query string", json.dumps({"query": ""}), []),
    ("whitespace query string", json.dumps({"query": "   "}), []),
    ("query wrong type, no wrapper", json.dumps({"query": 42}), []),
    ("no query, no tool_uses", json.dumps({"foo": "bar"}), []),
    ("top-level JSON is a list, not a dict", json.dumps(["query", "x"]), []),
    ("invalid JSON", "{not json", []),
    ("empty string", "", []),
    ("None argument", None, []),
]


def main():
    failures = 0
    for label, arguments, expected in CASES:
        got = q(arguments)
        ok = got == expected
        failures += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {label}")
        if not ok:
            print(f"        expected {expected!r}, got {got!r}")
    total = len(CASES)
    print(f"\n{total - failures}/{total} passed")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
