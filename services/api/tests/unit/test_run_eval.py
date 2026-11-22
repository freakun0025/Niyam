import importlib.util
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

CANDIDATES = [parent / "eval" for parent in Path(__file__).resolve().parents]
EVAL_DIR = next(path for path in CANDIDATES if (path / "run_eval.py").exists())
spec = importlib.util.spec_from_file_location("run_eval", EVAL_DIR / "run_eval.py")
run_eval = importlib.util.module_from_spec(spec)
sys.modules["run_eval"] = run_eval
spec.loader.exec_module(run_eval)


def case(case_id: str = "c1", **overrides: Any) -> dict[str, Any]:
    return {
        "id": case_id,
        "question": "What is the period?",
        "expected_doc_ids": ["doc-a"],
        "must_include": ["one day"],
        "should_refuse": False,
        "generate": True,
        "fixture": True,
        "corpus": False,
        **overrides,
    }


def refusal(case_id: str = "oos") -> dict[str, Any]:
    return case(
        case_id,
        question="Who won the match?",
        expected_doc_ids=[],
        must_include=[],
        should_refuse=True,
        generate=False,
        corpus=True,
    )


def transport(
    answer: str = "The period is one day [1].",
    refused: bool = False,
    doc_id: str = "doc-a",
    status: int = 200,
    seen: list[dict[str, Any]] | None = None,
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/version":
            return httpx.Response(200, json={"app_version": "a1b2c3d"})
        if status != 200:
            return httpx.Response(status, json={"error": "internal"})
        body = json.loads(request.content)
        if seen is not None:
            seen.append({"path": request.url.path, "body": body, "host": request.headers["host"]})
        if request.url.path == "/api/v1/search":
            return httpx.Response(200, json={"hits": [{"doc_id": doc_id}]})
        if "Who won" in body["question"]:
            return httpx.Response(200, json={"answer": "No.", "citations": [], "refused": True})
        citations = [] if refused else [{"n": 1}]
        return httpx.Response(
            200, json={"answer": answer, "citations": citations, "refused": refused}
        )

    return httpx.MockTransport(handler)


@pytest.fixture
def files(tmp_path: Path) -> Callable[..., list[str]]:
    def _files(*cases: dict[str, Any], stage: str = "ci") -> list[str]:
        golden = tmp_path / "golden.jsonl"
        golden.write_text("\n".join(json.dumps(item) for item in cases) + "\n", "utf-8")
        thresholds = tmp_path / "thresholds.yaml"
        limits = {
            "hit_at_k": 0.8,
            "keyword_recall": 0.6,
            "citation_rate": 0.9,
            "refusal_accuracy": 0.8,
            "p95_search_ms": 60000,
        }
        thresholds.write_text(yaml.safe_dump({"version": 1, "ci": limits, "live": limits}), "utf-8")
        return [
            "--base-url",
            "http://testserver",
            "--stage",
            stage,
            "--subset",
            "all",
            "--golden",
            str(golden),
            "--thresholds",
            str(thresholds),
            "--out",
            str(tmp_path / "results" / "out.json"),
        ]

    return _files


def saved(tmp_path: Path) -> dict[str, Any]:
    return json.loads((tmp_path / "results" / "out.json").read_text("utf-8"))


def test_passing_run_writes_results_and_log_event(
    files: Callable[..., list[str]], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run_eval.main(files(case(), refusal()), transport())

    assert code == run_eval.EXIT_PASS
    report = saved(tmp_path)
    assert report["app_version"] == "a1b2c3d"
    assert report["passed"] is True
    assert report["metrics"]["hit_at_k"] == 1
    assert report["metrics"]["keyword_recall"] == 1
    assert report["metrics"]["citation_rate"] == 1
    assert report["metrics"]["refusal_accuracy"] == 1
    assert report["failures"] == []
    captured = capsys.readouterr()
    event = json.loads(captured.out)
    assert event["event"] == "eval.result"
    assert event["service"] == "niyam-eval"
    assert event["app_version"] == "a1b2c3d"
    assert event["passed"] is True
    assert "RESULT: PASS" in captured.err


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"doc_id": "wrong-doc"}, "expected document not retrieved"),
        ({"answer": "The period is unknown [1]."}, "missing terms: one day"),
        ({"answer": "The period is one day."}, "no valid citation"),
        ({"refused": True}, "refused"),
    ],
)
def test_quality_failures_exit_one_with_reason(
    files: Callable[..., list[str]], tmp_path: Path, kwargs: dict[str, Any], reason: str
) -> None:
    code = run_eval.main(files(case()), transport(**kwargs))

    assert code == run_eval.EXIT_FAILED
    report = saved(tmp_path)
    assert report["passed"] is False
    assert any(item["id"] == "c1" and item["reason"] == reason for item in report["failures"])


def test_answering_an_off_topic_question_counts_as_failure(
    files: Callable[..., list[str]], tmp_path: Path
) -> None:
    item = refusal()
    item["question"] = "What is the capital?"

    assert run_eval.main(files(item), transport()) == run_eval.EXIT_FAILED
    assert saved(tmp_path)["failures"][0]["reason"] == "answered but should refuse"


@pytest.mark.parametrize("status", [500, 503])
def test_service_error_exits_two_without_a_verdict(
    files: Callable[..., list[str]], tmp_path: Path, status: int
) -> None:
    assert run_eval.main(files(case()), transport(status=status)) == run_eval.EXIT_ERROR
    assert not (tmp_path / "results" / "out.json").exists()


def test_unreachable_service_exits_two(files: Callable[..., list[str]]) -> None:
    def failing(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    assert run_eval.main(files(case()), httpx.MockTransport(failing)) == run_eval.EXIT_ERROR


def test_filters_and_host_header_are_sent(files: Callable[..., list[str]]) -> None:
    seen: list[dict[str, Any]] = []
    args = files(case(filters={"regulator": "RBI"})) + ["--host-header", "niyam.local"]

    run_eval.main(args, transport(seen=seen))

    assert {item["path"] for item in seen} == {"/api/v1/search", "/api/v1/ask"}
    assert all(item["body"]["filters"] == {"regulator": "RBI"} for item in seen)
    assert all(item["host"] == "niyam.local" for item in seen)


def test_non_generated_case_does_not_call_the_llm(files: Callable[..., list[str]]) -> None:
    seen: list[dict[str, Any]] = []

    run_eval.main(files(case(generate=False), refusal()), transport(seen=seen))

    assert [item["path"] for item in seen] == ["/api/v1/search", "/api/v1/ask"]
    assert "Who won" in seen[1]["body"]["question"]


@pytest.mark.parametrize(
    ("term", "text", "expected"),
    [
        ("one day", "It is ONE DAY.", True),
        ("five per cent|5%", "The cap is 5%.", True),
        ("five per cent|5%", "The cap is ten.", False),
        ("not", "The bank was notified.", False),
        ("not|cannot", "A bank cannot do this.", True),
        ("100", "Pay ₹100 per day.", True),
        ("21", "Within 210 days.", False),
    ],
)
def test_term_matching(term: str, text: str, expected: bool) -> None:
    assert run_eval.term_found(term, text) is expected


def test_percentile_uses_nearest_rank() -> None:
    assert run_eval.percentile_95(list(range(1, 21))) == 19
    assert run_eval.percentile_95([7]) == 7
    assert run_eval.percentile_95([]) is None


def test_thresholds_treat_latency_as_a_maximum() -> None:
    limits = {"hit_at_k": 0.8, "p95_search_ms": 100}

    assert run_eval.check_thresholds({"hit_at_k": 0.8, "p95_search_ms": 100}, limits) == []
    assert len(run_eval.check_thresholds({"hit_at_k": 0.7, "p95_search_ms": 101}, limits)) == 2
    assert run_eval.check_thresholds({"hit_at_k": None}, {"hit_at_k": 0.8}) == [
        "hit_at_k: not measured"
    ]


def test_subset_and_short_sample_keep_answering_and_refusing() -> None:
    cases = [case(f"a{n}", corpus=True) for n in range(8)] + [refusal(f"r{n}") for n in range(3)]

    assert len(run_eval.select_cases(cases, "corpus")) == 11
    sample = run_eval.select_cases(cases, "corpus", limit=5)

    assert len(sample) == 5
    assert sum(item["should_refuse"] for item in sample) == 1


@pytest.mark.parametrize(
    "bad",
    [
        '{"id": "x"}',
        "not json",
        json.dumps(case("x", expected_doc_ids=[])),
        json.dumps(case("x")) + "\n" + json.dumps(case("x")),
    ],
)
def test_invalid_golden_files_are_rejected(tmp_path: Path, bad: str) -> None:
    path = tmp_path / "golden.jsonl"
    path.write_text(bad + "\n", "utf-8")

    with pytest.raises(run_eval.EvalError):
        run_eval.load_cases(path)


def test_repository_golden_set_is_valid() -> None:
    cases = run_eval.load_cases(EVAL_DIR / "golden.jsonl")

    assert 25 <= len(cases) <= 35
    for subset in ("fixture", "corpus"):
        selected = run_eval.select_cases(cases, subset)
        assert any(item["should_refuse"] for item in selected)
        assert any(not item["should_refuse"] for item in selected)

    root = EVAL_DIR.parent
    for subset, folder in (("fixture", "fixtures"), ("corpus", "corpus")):
        manifest = root / "data" / folder / "manifest.yaml"
        if not manifest.exists():
            continue
        known = {doc["doc_id"] for doc in yaml.safe_load(manifest.read_text("utf-8"))["documents"]}
        for item in run_eval.select_cases(cases, subset):
            assert set(item["expected_doc_ids"]) <= known, item["id"]
