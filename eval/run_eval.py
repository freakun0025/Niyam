#!/usr/bin/env python3
"""Measure answer quality against the golden questions.

Exit codes: 0 = all thresholds met, 1 = a threshold failed, 2 = setup or service error.
The readable report goes to stderr. Stdout carries one JSON eval.result log event.
"""

import argparse
import json
import math
import re
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

EXIT_PASS = 0
EXIT_FAILED = 1
EXIT_ERROR = 2

EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_SUBSET = {"ci": "fixture", "live": "corpus"}
TOP_K = 6
SEARCH_TIMEOUT_SECONDS = 15
ASK_TIMEOUT_SECONDS = 130
REQUIRED_FIELDS = {
    "id",
    "question",
    "expected_doc_ids",
    "must_include",
    "should_refuse",
    "generate",
    "fixture",
    "corpus",
}
METRIC_NAMES = (
    "hit_at_k",
    "keyword_recall",
    "citation_rate",
    "refusal_accuracy",
    "p95_search_ms",
    "p95_ask_ms",
)


class EvalError(RuntimeError):
    """The evaluation could not run, so no quality verdict exists."""


@dataclass
class CaseResult:
    case: dict[str, Any]
    hit: bool | None = None
    search_ms: int | None = None
    ask_ms: int | None = None
    refused: bool | None = None
    keyword_recall: float | None = None
    cited: bool | None = None
    reasons: list[str] = field(default_factory=list)


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise EvalError(f"cannot read golden file: {exc}") from exc

    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvalError(f"{path.name} line {number}: invalid JSON") from exc
        missing = REQUIRED_FIELDS - case.keys()
        if missing:
            raise EvalError(f"{path.name} line {number}: missing {sorted(missing)}")
        if not case["should_refuse"] and not case["expected_doc_ids"]:
            raise EvalError(f"{case['id']}: answerable cases need expected_doc_ids")
        cases.append(case)

    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise EvalError("golden case ids must be unique")
    if not cases:
        raise EvalError("golden file has no cases")
    return cases


def select_cases(
    cases: Sequence[dict[str, Any]], subset: str, limit: int | None = None
) -> list[dict[str, Any]]:
    if subset == "all":
        selected = list(cases)
    else:
        selected = [case for case in cases if case[subset]]
    if not selected:
        raise EvalError(f"no golden cases in subset: {subset}")
    if limit is None or limit >= len(selected):
        return selected

    # A short live check must still test both answering and refusing.
    answerable = [case for case in selected if not case["should_refuse"]]
    refusals = [case for case in selected if case["should_refuse"]]
    refusal_count = min(len(refusals), max(1, limit // 5))
    answer_count = min(len(answerable), limit - refusal_count)
    return answerable[:answer_count] + refusals[: limit - answer_count]


def term_found(term: str, text: str) -> bool:
    """Match whole words, so "not" does not match "notified". | separates accepted spellings."""
    return any(
        re.search(rf"(?<!\w){re.escape(option.strip())}(?!\w)", text, re.IGNORECASE)
        for option in term.split("|")
    )


def percentile_95(values: Sequence[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


class ApiClient:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def request(self, method: str, path: str, timeout: float, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self.client.request(method, path, timeout=timeout, **kwargs)
        except httpx.HTTPError as exc:
            raise EvalError(f"{path}: cannot reach service: {type(exc).__name__}") from exc
        if response.status_code != 200:
            raise EvalError(f"{path}: unexpected HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise EvalError(f"{path}: response is not JSON") from exc


def _request_body(case: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {"question": case["question"], "top_k": TOP_K}
    if case.get("filters"):
        body["filters"] = case["filters"]
    return body


def evaluate_case(api: ApiClient, case: dict[str, Any]) -> CaseResult:
    result = CaseResult(case=case)
    body = _request_body(case)

    if not case["should_refuse"]:
        started = time.perf_counter()
        search = api.request("POST", "/api/v1/search", SEARCH_TIMEOUT_SECONDS, json=body)
        result.search_ms = round((time.perf_counter() - started) * 1000)
        found = {hit["doc_id"] for hit in search["hits"]}
        result.hit = bool(found.intersection(case["expected_doc_ids"]))
        if not result.hit:
            result.reasons.append("expected document not retrieved")

    if not (case["generate"] or case["should_refuse"]):
        return result

    started = time.perf_counter()
    answer = api.request("POST", "/api/v1/ask", ASK_TIMEOUT_SECONDS, json=body)
    result.ask_ms = round((time.perf_counter() - started) * 1000)
    result.refused = bool(answer["refused"])
    if result.refused != case["should_refuse"]:
        result.reasons.append("answered but should refuse" if not result.refused else "refused")

    if case["should_refuse"]:
        return result

    terms = case["must_include"]
    missing = [term for term in terms if not term_found(term, answer["answer"])]
    if result.refused:
        result.keyword_recall = 0.0
    else:
        result.keyword_recall = (len(terms) - len(missing)) / len(terms) if terms else 1.0
        valid = {citation["n"] for citation in answer["citations"]}
        markers = {int(number) for number in re.findall(r"\[(\d+)\]", answer["answer"])}
        result.cited = bool(valid & markers)
        if not result.cited:
            result.reasons.append("no valid citation")
        if missing:
            result.reasons.append(f"missing terms: {', '.join(missing)}")
    return result


def _mean(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def compute_metrics(results: Sequence[CaseResult]) -> dict[str, float | int | None]:
    hits = [result.hit for result in results if result.hit is not None]
    keywords = [r.keyword_recall for r in results if r.keyword_recall is not None]
    citations = [result.cited for result in results if result.cited is not None]
    refusals = [
        result.refused == result.case["should_refuse"]
        for result in results
        if result.refused is not None
    ]
    return {
        "hit_at_k": _mean([float(value) for value in hits]),
        "keyword_recall": _mean(keywords),
        "citation_rate": _mean([float(value) for value in citations]),
        "refusal_accuracy": _mean([float(value) for value in refusals]),
        "p95_search_ms": percentile_95([r.search_ms for r in results if r.search_ms is not None]),
        "p95_ask_ms": percentile_95([r.ask_ms for r in results if r.ask_ms is not None]),
    }


def check_thresholds(
    metrics: dict[str, float | int | None], thresholds: dict[str, float]
) -> list[str]:
    failures: list[str] = []
    for name, limit in thresholds.items():
        value = metrics.get(name)
        if value is None:
            failures.append(f"{name}: not measured")
        elif name.startswith("p95_") and value > limit:
            failures.append(f"{name}: {value} is above {limit}")
        elif not name.startswith("p95_") and value < limit:
            failures.append(f"{name}: {value} is below {limit}")
    return failures


def load_thresholds(path: Path, stage: str) -> tuple[dict[str, float], Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return raw[stage], raw["version"]
    except (OSError, yaml.YAMLError, KeyError, TypeError) as exc:
        raise EvalError(f"invalid thresholds file: {exc}") from exc


def print_report(report: dict[str, Any]) -> None:
    lines = [
        "",
        f"Eval: {report['app_version']}  stage={report['stage']}  "
        f"subset={report['subset']}  cases={report['cases']}",
        f"{'metric':<20}{'value':>10}{'limit':>10}  status",
    ]
    for name in METRIC_NAMES:
        value = report["metrics"][name]
        limit = report["thresholds"].get(name)
        if limit is None:
            status = "info"
        elif check_thresholds({name: value}, {name: limit}):
            status = "FAIL"
        else:
            status = "ok"
        shown_value = "n/a" if value is None else value
        shown_limit = "-" if limit is None else limit
        lines.append(f"{name:<20}{shown_value!s:>10}{shown_limit!s:>10}  {status}")
    for failure in report["failures"]:
        lines.append(f"  {failure['id']}: {failure['reason']}")
    lines.append(f"RESULT: {'PASS' if report['passed'] else 'FAIL'}")
    sys.stderr.write("\n".join(lines) + "\n")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Niyam against the golden questions.")
    parser.add_argument("--base-url", required=True, help="for example http://localhost:8000")
    parser.add_argument("--stage", choices=("ci", "live"), default="ci")
    parser.add_argument("--subset", choices=("fixture", "corpus", "all"))
    parser.add_argument("--limit", type=int, help="run a short balanced sample")
    parser.add_argument("--host-header", help="Host header, for an ingress reached by IP")
    parser.add_argument("--golden", type=Path, default=EVAL_DIR / "golden.jsonl")
    parser.add_argument("--thresholds", type=Path, default=EVAL_DIR / "thresholds.yaml")
    parser.add_argument("--out", type=Path, help="default: eval/results/<app_version>.json")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 2:
        parser.error("--limit must be at least 2")
    return args


def run(args: argparse.Namespace, transport: httpx.BaseTransport | None = None) -> int:
    started_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    subset = args.subset or DEFAULT_SUBSET[args.stage]
    cases = select_cases(load_cases(args.golden), subset, args.limit)
    thresholds, thresholds_version = load_thresholds(args.thresholds, args.stage)
    headers = {"Host": args.host_header} if args.host_header else {}

    with httpx.Client(base_url=args.base_url, headers=headers, transport=transport) as client:
        api = ApiClient(client)
        app_version = api.request("GET", "/version", SEARCH_TIMEOUT_SECONDS)["app_version"]
        results = [evaluate_case(api, case) for case in cases]

    metrics = compute_metrics(results)
    threshold_failures = check_thresholds(metrics, thresholds)
    failures = [
        {"id": result.case["id"], "reason": reason}
        for result in results
        for reason in result.reasons
    ]
    failures += [{"id": "threshold", "reason": reason} for reason in threshold_failures]
    passed = not threshold_failures
    report = {
        "app_version": app_version,
        "stage": args.stage,
        "subset": subset,
        "started_at": started_at,
        "passed": passed,
        "cases": len(results),
        "metrics": metrics,
        "thresholds": thresholds,
        "thresholds_version": thresholds_version,
        "failures": failures,
    }

    out = args.out or EVAL_DIR / "results" / f"{app_version}.json"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise EvalError(f"cannot write results: {exc}") from exc

    print_report(report)
    event = {
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "level": "INFO" if passed else "ERROR",
        "service": "niyam-eval",
        "app_version": app_version,
        "event": "eval.result",
        "stage": args.stage,
        "passed": passed,
        "metrics": metrics,
        "thresholds_version": thresholds_version,
        "cases": len(results),
    }
    sys.stdout.write(json.dumps(event, separators=(",", ":")) + "\n")
    return EXIT_PASS if passed else EXIT_FAILED


def main(argv: Sequence[str] | None = None, transport: httpx.BaseTransport | None = None) -> int:
    args = parse_args(argv)
    try:
        return run(args, transport)
    except EvalError as exc:
        sys.stderr.write(f"EVAL ERROR: {exc}\n")
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
