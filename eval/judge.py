"""RAGAS faithfulness and answer relevancy, and a rubric LLM judge, on a free-tier judge model
(eval/answer_eval_protocol.md, sections 4.4-4.7, 5 and 7, and its dated deviations).

    python -m eval.judge plan [--set judge-check|benchmark]       # what is left and what it costs; no LLM
    python -m eval.judge run --set judge-check|benchmark --max-requests N [--env-file PATH]
    python -m eval.judge summarize                                 # writes eval/results/judge_summary.json

The judge is configurable:
    JUDGE_PROVIDER  openrouter (default) or gemini
    JUDGE_MODEL     default: DEFAULT_OPENROUTER_MODEL for openrouter; GEMINI_MODEL for gemini
OpenRouter is the default so Gemini, which wrote the answers, doesn't grade its own work. It is called
over plain HTTP (eval/openrouter.py) with OPENROUTER_API_KEY; free model IDs and limits change, so
check them before a run. Gemini stays available through llm.generate_text, with the app's retry limits.

Every HTTP request is counted where it is sent, retries included: for OpenRouter in eval/openrouter.py
before each attempt, for Gemini at BaseApiClient._request_once (as eval/ask_live.py does). A run never
sends more than --max-requests requests, and starts an item only if its unfinished metrics fit in what
is left. Each metric of each item is cached under eval/results/judge/, keyed by item, answer hash,
judge provider and model, metric and prompt hash, so runs resume across days and nothing is judged
twice. Only synthetic resumes are involved. Scores are the judge model's opinion, not ground truth.

RAGAS reaches the judge through an adapter: a subclass of ragas.llms.base.InstructorBaseRagasLLM whose
generate/agenerate send RAGAS's own prompt to the judge and validate the JSON reply against RAGAS's
output model (one request per call; the instructor client and its re-asks are not used). Answer
relevancy embeds with the local all-MiniLM-L6-v2 model, so it costs no requests.
"""
import argparse
import datetime
import hashlib
import importlib.metadata as md
import json
import math
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any, TypeVar

from pydantic import BaseModel

import llm
from eval.answers import ANSWERED, select_answers
from eval.benchmark import ROOT, chunks_by_resume, resolve
from eval.golden import load_golden, load_heldout

OPENROUTER, GEMINI = "openrouter", "gemini"
PROVIDERS = (OPENROUTER, GEMINI)
DEFAULT_PROVIDER = OPENROUTER
# A free instruct model from another family than the Gemini model that wrote the answers. Free model
# IDs come and go: check https://openrouter.ai/models?max_price=0 and set JUDGE_MODEL if this one is gone.
DEFAULT_OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
RAGAS_VERSION = "0.4.3"
RELEVANCY_STRICTNESS = 1             # RAGAS's default is 3; 1 fits the request budget (protocol 4.5)
PACING_SECONDS = 6.0                 # between judge calls: at most 10 a minute, under free per-minute limits
# Free requests a day, for the plan's estimate only (--max-requests is what a run obeys). Gemini's
# 20 are shared with the ask runs. OpenRouter's free limit was 50 a day without purchased credits
# (1000 with at least 10 credits) when this was written; check https://openrouter.ai/docs/api-reference/limits.
DAILY_QUOTA = {GEMINI: 20, OPENROUTER: 50}

PROTOCOL = ROOT / "eval" / "answer_eval_protocol.md"
RESULTS_DIR = ROOT / "eval" / "results"
CACHE_DIR = RESULTS_DIR / "judge"
RUNS_LOG = RESULTS_DIR / "judge_runs.jsonl"
SUMMARY_JSON = RESULTS_DIR / "judge_summary.json"
SETS = ("judge-check", "benchmark")

FAITHFULNESS, RELEVANCY, RUBRIC = "faithfulness", "answer_relevancy", "rubric"
# Requests per metric when nothing is retried: faithfulness makes two calls (statements, then verdicts).
METRIC_REQUESTS = {FAITHFULNESS: 2, RELEVANCY: 1, RUBRIC: 1}
NO_KEY_FACTS = "(none: no resume answers this question)"

# A run refuses to start if any of these has uncommitted changes, so the commit recorded is what judged.
JUDGE_INPUTS = ["eval/judge.py", "eval/openrouter.py", "eval/answers.py", "eval/golden.py", "eval/benchmark.py",
                "eval/golden.json", "eval/heldout.json", "eval/answer_eval_protocol.md", "eval/retrieval_benchmark.json",
                "eval/ask_live_batch*.json", "llm.py", "config.py", "embeddings.py", "chunking.py", "sample_resumes"]

M = TypeVar("M", bound=BaseModel)


# --- items -----------------------------------------------------------------------------------
@dataclass(frozen=True)
class Excerpt:
    number: int
    candidate: str
    section: str
    text: str


@dataclass(frozen=True)
class KeyFact:
    id: str
    candidate: str
    resume: str
    fact: str


@dataclass(frozen=True)
class Item:
    set: str                  # "benchmark" or "judge-check"
    item_id: str              # "q01"; "h01.good" / "h01.flawed"
    question_id: str
    kind: str                 # benchmark: "positive" or "negative"; judge check: "good" or the flaw
    question: str
    answer: str
    excerpts: tuple[Excerpt, ...]
    reference: str
    key_facts: tuple[KeyFact, ...]
    notes: str
    metrics: tuple[str, ...]
    commit: str | None = None  # the commit that generated the answer (benchmark)

    def answer_hash(self) -> str:
        payload = [self.question, self.answer, [[e.number, e.candidate, e.section, e.text] for e in self.excerpts]]
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode("utf-8")).hexdigest()


def benchmark_items() -> list[Item]:
    """One item per answered benchmark row (protocol sections 2-3); refusals and passages cost nothing."""
    golden = load_golden()
    reference = {q["id"]: q for q in golden["questions"] + golden["negative_questions"]}
    items = []
    for answer in select_answers():
        if answer.outcome != ANSWERED or answer.row is None:
            continue
        gold = reference[answer.question_id]
        facts = tuple(KeyFact(f["id"], f["candidate"], f["resume"], f["fact"]) for f in gold.get("key_facts", []))
        excerpts = tuple(Excerpt(int(c["number"]), str(c["candidate"]), str(c["section"]), str(c["text"]))
                         for c in answer.row.get("citations", []))
        items.append(Item("benchmark", answer.question_id, answer.question_id, answer.kind, answer.question,
                          str(answer.row.get("answer") or ""), excerpts, gold["reference_answer"], facts,
                          gold["rationale"], (FAITHFULNESS, RELEVANCY, RUBRIC), answer.commit))
    return items


def judge_check_items() -> list[Item]:
    """A good and a flawed answer per held-out answerable question (protocol section 4.7)."""
    corpus = chunks_by_resume()
    items = []
    for q in load_heldout()["answerable"]:
        excerpts, facts = [], []
        for i, label in enumerate(q["relevant"], start=1):
            (match,) = resolve(label, corpus)  # eval.golden validate guarantees exactly one
            excerpts.append(Excerpt(i, match.resume, match.chunk.section, match.chunk.text))
            facts.append(KeyFact(f"{q['id']}.f{i}", label["candidate"], label["resume"],
                                 f"{label['section']}: \"{label['contains']}\""))
        names = list(dict.fromkeys(label["candidate"] for label in q["relevant"]))
        reference = "Expected candidates: " + ", ".join(names) + "."
        check = q["judge_check"]
        for variant, kind, text in (("good", "good", check["good_answer"]),
                                    ("flawed", check["flaw"], check["flawed_answer"])):
            items.append(Item("judge-check", f"{q['id']}.{variant}", q["id"], kind, q["question"], text,
                              tuple(excerpts), reference, tuple(facts), q["rationale"], (RUBRIC,)))
    return items


def items_for(set_name: str) -> list[Item]:
    return judge_check_items() if set_name == "judge-check" else benchmark_items()


# --- the rubric prompt (read from the frozen protocol) ----------------------------------------
_PROMPT_BLOCK = re.compile(r"<!-- judge-prompt:start -->\s*```text\n(.*?)\n```\s*<!-- judge-prompt:end -->", re.S)


def rubric_prompt() -> str:
    text = PROTOCOL.read_text(encoding="utf-8").replace("\r\n", "\n")
    match = _PROMPT_BLOCK.search(text)
    if match is None:
        raise SystemExit(f"no judge prompt between the markers in {PROTOCOL.relative_to(ROOT)}")
    return match.group(1)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fill_prompt(template: str, item: Item) -> str:
    facts = "\n".join(f"- {f.id}: {f.candidate} ({f.resume}): {f.fact}" for f in item.key_facts) or NO_KEY_FACTS
    excerpts = "\n\n".join(f"[{e.number}] {e.candidate} ({e.section}):\n{e.text}" for e in item.excerpts)
    return Template(template).substitute(question=item.question, reference=item.reference, key_facts=facts,
                                         notes=item.notes, answer=item.answer, excerpts=excerpts or "(none)")


class Verdict(BaseModel):
    correctness: int
    key_facts_covered: list[str]
    citation_support: int
    invented_claims: list[str]
    reason: str


_VERDICT_KEYS = {"correctness", "key_facts_covered", "citation_support", "invented_claims", "reason"}


def parse_verdict(raw: str, fact_ids: set[str]) -> Verdict:
    """Strict: one JSON object with exactly the five keys and the protocol's types. Raises ValueError."""
    data = llm.parse_json_response(raw)
    if not isinstance(data, dict) or set(data) != _VERDICT_KEYS:
        raise ValueError(f"expected exactly the keys {sorted(_VERDICT_KEYS)}")
    for key in ("correctness", "citation_support"):
        if type(data[key]) is not int or data[key] not in (0, 1, 2):
            raise ValueError(f"{key} must be the integer 0, 1 or 2")
    for key in ("key_facts_covered", "invented_claims"):
        if not isinstance(data[key], list) or not all(isinstance(v, str) for v in data[key]):
            raise ValueError(f"{key} must be a list of strings")
    if not isinstance(data["reason"], str) or not data["reason"].strip():
        raise ValueError("reason must be a non-empty string")
    unknown = set(data["key_facts_covered"]) - fact_ids
    if unknown:
        raise ValueError(f"unknown key-fact ids {sorted(unknown)}")
    return Verdict.model_validate(data)


# --- judge configuration -----------------------------------------------------------------------
@dataclass(frozen=True)
class JudgeConfig:
    provider: str   # "openrouter" or "gemini"
    model: str      # the model ID sent to that provider

    @property
    def label(self) -> str:
        return f"{self.model} via {self.provider}"


def judge_config() -> JudgeConfig:
    """JUDGE_PROVIDER and JUDGE_MODEL from the environment (config.py loads .env first)."""
    import config

    provider = (os.getenv("JUDGE_PROVIDER") or DEFAULT_PROVIDER).strip().lower()
    if provider not in PROVIDERS:
        raise SystemExit(f"JUDGE_PROVIDER must be one of {', '.join(PROVIDERS)}, not {provider!r}")
    model = (os.getenv("JUDGE_MODEL") or "").strip()
    if provider == GEMINI:
        # llm.generate_text always calls config.GEMINI_MODEL, so the two must agree.
        if model and model != config.GEMINI_MODEL:
            raise SystemExit(f"JUDGE_MODEL is {model} but llm.py calls GEMINI_MODEL={config.GEMINI_MODEL}; "
                             "set GEMINI_MODEL instead, or leave JUDGE_MODEL unset")
        return JudgeConfig(GEMINI, config.GEMINI_MODEL)
    return JudgeConfig(OPENROUTER, model or DEFAULT_OPENROUTER_MODEL)


# --- request accounting ------------------------------------------------------------------------
class BudgetExhausted(RuntimeError):
    """The next judge request would go over --max-requests; it was not sent."""


class RequestCounter:
    """Counts every HTTP request to the judge where it is sent, retries included, and refuses to
    send one past the limit. OpenRouter calls take() before each attempt (eval/openrouter.py); for
    Gemini, install() wraps the SDK's request method."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.sent = 0

    @property
    def remaining(self) -> int:
        return self.limit - self.sent

    def take(self) -> None:
        if self.sent >= self.limit:
            raise BudgetExhausted(f"the limit of {self.limit} requests is reached")
        self.sent += 1

    def install(self) -> Callable[[], None]:
        """Wrap BaseApiClient._request_once (and its async twin); returns a function that restores them."""
        from google.genai import _api_client

        cls = _api_client.BaseApiClient
        real_sync, real_async = cls._request_once, cls._async_request_once

        def counting(client: Any, *args: Any, **kwargs: Any) -> Any:
            self.take()
            return real_sync(client, *args, **kwargs)

        async def counting_async(client: Any, *args: Any, **kwargs: Any) -> Any:
            self.take()
            return await real_async(client, *args, **kwargs)

        cls._request_once = counting  # type: ignore[method-assign,assignment]
        cls._async_request_once = counting_async  # type: ignore[method-assign,assignment]

        def uninstall() -> None:
            cls._request_once = real_sync  # type: ignore[method-assign]
            cls._async_request_once = real_async  # type: ignore[method-assign]
        return uninstall


def gemini_sender(api_key: str) -> Callable[[str], str]:
    """Send through llm.generate_text, looked up at call time so tests can fence it."""
    def send(prompt: str) -> str:
        return llm.generate_text(prompt, api_key)
    return send


def openrouter_sender(api_key: str, model: str, counter: RequestCounter,
                      served: list[str]) -> Callable[[str], str]:
    """Send through eval/openrouter.py; counter.take() runs before every HTTP attempt. Appends the
    model (and upstream provider) OpenRouter reports to `served`."""
    from eval.openrouter import OpenRouterClient

    client = OpenRouterClient(api_key, model, before_request=counter.take)

    def send(prompt: str) -> str:
        completion = client.complete(prompt)
        served.append(f"{completion.model or model}" + (f" ({completion.provider})" if completion.provider else ""))
        return completion.text
    return send


class Judge:
    """Every judge call: pacing, then the provider's sender."""

    def __init__(self, send: Callable[[str], str], pacing: float = PACING_SECONDS) -> None:
        self.send = send
        self.pacing = pacing
        self._last = -math.inf

    def text(self, prompt: str) -> str:
        wait = self.pacing - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        try:
            return self.send(prompt)
        finally:
            self._last = time.monotonic()

    def structured(self, prompt: str, model: type[M]) -> M:
        """RAGAS's structured call: its prompt already asks for JSON matching the output model's schema."""
        return model.model_validate(llm.parse_json_response(self.text(prompt)))


# --- RAGAS -------------------------------------------------------------------------------------
@dataclass
class RagasMetrics:
    faithfulness: Any
    relevancy: Any
    version: str


def ragas_metrics(judge: Judge) -> RagasMetrics:
    """RAGAS's collections Faithfulness and AnswerRelevancy, wired to the configured judge."""
    os.environ["RAGAS_DO_NOT_TRACK"] = "true"  # ragas otherwise sends usage analytics
    try:
        from ragas.embeddings.base import BaseRagasEmbedding
        from ragas.llms.base import InstructorBaseRagasLLM
        from ragas.metrics.collections import AnswerRelevancy, Faithfulness
    except ImportError as exc:
        raise SystemExit(f"ragas is not usable ({exc}); install it with: pip install -r requirements-eval.txt") from exc
    version = md.version("ragas")
    if version != RAGAS_VERSION:
        raise SystemExit(f"the protocol pins ragas {RAGAS_VERSION}, but {version} is installed")
    from embeddings import SentenceTransformerProvider

    provider = SentenceTransformerProvider()

    def generate(self: Any, prompt: str, response_model: type[BaseModel]) -> BaseModel:
        return judge.structured(prompt, response_model)

    async def agenerate(self: Any, prompt: str, response_model: type[BaseModel]) -> BaseModel:
        return judge.structured(prompt, response_model)

    def embed_text(self: Any, text: str, **kwargs: Any) -> list[float]:
        return provider.embed([text], kind="query")[0]

    async def aembed_text(self: Any, text: str, **kwargs: Any) -> list[float]:
        return provider.embed([text], kind="query")[0]

    # Built with type() so this module imports, and type-checks, without ragas installed.
    judge_llm = type("JudgeRagasLLM", (InstructorBaseRagasLLM,),
                     {"generate": generate, "agenerate": agenerate})()
    local_embeddings = type("LocalRagasEmbedding", (BaseRagasEmbedding,),
                            {"embed_text": embed_text, "aembed_text": aembed_text})()
    return RagasMetrics(Faithfulness(llm=judge_llm),
                        AnswerRelevancy(llm=judge_llm, embeddings=local_embeddings,
                                        strictness=RELEVANCY_STRICTNESS),
                        version)


# --- cache -------------------------------------------------------------------------------------
def prompt_id(metric: str, rubric_sha: str) -> str:
    if metric == RUBRIC:
        return rubric_sha
    suffix = f"-strictness{RELEVANCY_STRICTNESS}" if metric == RELEVANCY else ""
    return f"ragas-{RAGAS_VERSION}-{metric}{suffix}"


def cache_path(item: Item, metric: str, rubric_sha: str, cfg: JudgeConfig) -> Path:
    key = sha256(json.dumps([item.set, item.item_id, item.answer_hash(), cfg.provider, cfg.model, metric,
                             prompt_id(metric, rubric_sha)]))[:16]
    return CACHE_DIR / item.set / f"{item.item_id}__{metric}__{key}.json"


def pending_metrics(item: Item, rubric_sha: str, cfg: JudgeConfig) -> list[str]:
    return [m for m in item.metrics if not cache_path(item, m, rubric_sha, cfg).exists()]


def load_cache() -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CACHE_DIR.glob("*/*.json"))]


# --- running -----------------------------------------------------------------------------------
def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def judge_metric(metric: str, item: Item, judge: Judge, template: str,
                 ragas: Callable[[], RagasMetrics]) -> dict[str, Any]:
    """Score one metric of one item. Raises BudgetExhausted, or the API error after the retries;
    a reply that doesn't parse is returned as a recorded result, not raised."""
    if metric == RUBRIC:
        raw = judge.text(fill_prompt(template, item))
        try:
            verdict = parse_verdict(raw, {f.id for f in item.key_facts})
        except ValueError as exc:
            return {"status": "parse_error", "error": str(exc)[:300], "raw": raw}
        return {"status": "ok", "verdict": verdict.model_dump(), "raw": raw}
    metrics = ragas()
    try:
        if metric == FAITHFULNESS:
            result = metrics.faithfulness.score(user_input=item.question, response=item.answer,
                                                retrieved_contexts=[e.text for e in item.excerpts])
        else:
            result = metrics.relevancy.score(user_input=item.question, response=item.answer)
    except ValueError as exc:  # pydantic and JSON errors: the judge's reply didn't match RAGAS's schema
        return {"status": "parse_error", "error": f"{type(exc).__name__}: {str(exc)[:300]}"}
    value = float(result.value)
    if math.isnan(value):
        return {"status": "undefined", "value": None, "note": "RAGAS returned NaN (no statements extracted)"}
    return {"status": "ok", "value": value}


def _load_env(env_file: str | None, name: str) -> None:
    from eval.ask_live import load_env_var

    load_env_var(env_file, name)


def _api_key(cfg: JudgeConfig, env_file: str | None) -> str:
    import config

    if cfg.provider == GEMINI:
        _load_env(env_file, "GOOGLE_API_KEY")
        key = config.get_api_key()
        if not key:
            raise SystemExit("no Gemini API key configured (GOOGLE_API_KEY)")
        return str(key)
    _load_env(env_file, "OPENROUTER_API_KEY")
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise SystemExit("no OpenRouter API key configured (OPENROUTER_API_KEY)")
    return key


def make_judge(cfg: JudgeConfig, api_key: str, counter: RequestCounter,
               served: list[str]) -> tuple[Judge, Callable[[], None]]:
    """The judge for this configuration, and a function that undoes its request counting."""
    if cfg.provider == GEMINI:
        return Judge(gemini_sender(api_key)), counter.install()
    return Judge(openrouter_sender(api_key, cfg.model, counter, served)), lambda: None


def run(set_name: str, max_requests: int, env_file: str | None) -> dict[str, Any]:
    commit = _git("rev-parse", "--short", "HEAD")
    dirty = _git("status", "--porcelain", "--", *JUDGE_INPUTS)
    if dirty:
        raise SystemExit(f"uncommitted changes in the judge or its inputs; commit them first:\n{dirty}")
    if max_requests < 1:
        raise SystemExit("--max-requests must be at least 1")
    cfg = judge_config()
    api_key = _api_key(cfg, env_file)

    template = rubric_prompt()
    rubric_sha = sha256(template)
    work = [(item, pending_metrics(item, rubric_sha, cfg)) for item in items_for(set_name)]
    work = [(item, metrics) for item, metrics in work if metrics]
    started = datetime.datetime.now().isoformat(timespec="seconds")
    counter = RequestCounter(max_requests)
    served: list[str] = []
    judge, uninstall = make_judge(cfg, api_key, counter, served)
    loaded: list[RagasMetrics] = []

    def ragas() -> RagasMetrics:
        if not loaded:
            loaded.append(ragas_metrics(judge))
        return loaded[0]

    done, stopped = 0, "finished: nothing left to judge in this set"
    try:
        for item, metrics in work:
            need = sum(METRIC_REQUESTS[m] for m in metrics)
            if need > counter.remaining:
                stopped = f"budget: {counter.remaining} request(s) left, the next item needs {need}"
                break
            stop = _judge_item(item, metrics, judge, template, rubric_sha, counter, ragas, commit, cfg, served)
            if stop:
                stopped = stop
                break
            done += 1
            print(f"{item.set} {item.item_id}: {', '.join(metrics)} ({counter.sent} requests so far)", flush=True)
    finally:
        uninstall()
        record = {"started": started, "commit": commit, "set": set_name, "judge_provider": cfg.provider,
                  "judge_model": cfg.model, "max_requests": max_requests, "requests_sent": counter.sent,
                  "items_completed": done, "items_pending_at_start": len(work), "stopped": stopped}
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        with RUNS_LOG.open("a", encoding="utf-8") as log:
            log.write(json.dumps(record) + "\n")
    print(f"{counter.sent} {cfg.provider} request(s) sent; {stopped}")
    return record


def _judge_item(item: Item, metrics: list[str], judge: Judge, template: str, rubric_sha: str,
                counter: RequestCounter, ragas: Callable[[], RagasMetrics], commit: str, cfg: JudgeConfig,
                served: list[str]) -> str | None:
    """Judge and cache each pending metric of one item; returns why the run must stop, or None."""
    for metric in metrics:
        before, served_before = counter.sent, len(served)
        try:
            result = judge_metric(metric, item, judge, template, ragas)
        except BudgetExhausted as exc:
            return f"budget: {exc} (during {item.item_id} {metric}; not cached, retried next run)"
        except Exception as exc:  # the API failed after the retries: try again another day
            return (f"{type(exc).__name__} during {item.item_id} {metric}: {str(exc)[:200]} "
                    "(not cached, retried next run)")
        entry = {"set": item.set, "item_id": item.item_id, "question_id": item.question_id, "kind": item.kind,
                 "metric": metric, "judge_provider": cfg.provider, "judge_model": cfg.model,
                 "served_by": sorted(set(served[served_before:])), "answer_sha256": item.answer_hash(),
                 "prompt": prompt_id(metric, rubric_sha), "answer_commit": item.commit,
                 "judged_at_commit": commit, "date": datetime.date.today().isoformat(),
                 "requests": counter.sent - before, **result}
        path = cache_path(item, metric, rubric_sha, cfg)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return None


# --- plan and summary --------------------------------------------------------------------------
def plan(set_names: list[str], cfg: JudgeConfig) -> dict[str, Any]:
    rubric_sha = sha256(rubric_prompt())
    out: dict[str, Any] = {}
    for name in set_names:
        items = items_for(name)
        pending = [(item, pending_metrics(item, rubric_sha, cfg)) for item in items]
        cost = sum(METRIC_REQUESTS[m] for _, metrics in pending for m in metrics)
        out[name] = {"items": len(items), "items_pending": sum(1 for _, m in pending if m),
                     "requests_needed_without_retries": cost}
    return out


def agrees(expected: str, verdict: dict[str, Any]) -> bool:
    """Does the judge's verdict match what the judge-check item was written to show (protocol 4.7)?"""
    if expected == "good":
        return bool(verdict["correctness"] == 2 and verdict["citation_support"] == 2
                    and not verdict["invented_claims"])
    if expected == "omission":
        return bool(verdict["correctness"] <= 1)
    if expected == "invented_claim":
        return bool(verdict["invented_claims"])
    return bool(verdict["citation_support"] <= 1)  # wrong_citation


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _per_question(answered: list[Item], bench: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each answered benchmark row's cached results (None where not judged yet)."""
    rows = []
    for item in answered:
        found = {e["metric"]: e for e in bench if e["item_id"] == item.item_id
                 and e["answer_sha256"] == item.answer_hash()}
        verdict = (found.get(RUBRIC) or {}).get("verdict")
        rows.append({"id": item.item_id, "kind": item.kind, "answer_commit": item.commit,
                     "faithfulness": (found.get(FAITHFULNESS) or {}).get("value"),
                     "faithfulness_status": (found.get(FAITHFULNESS) or {}).get("status"),
                     "answer_relevancy": (found.get(RELEVANCY) or {}).get("value"),
                     "answer_relevancy_status": (found.get(RELEVANCY) or {}).get("status"),
                     "rubric_status": (found.get(RUBRIC) or {}).get("status"),
                     "correctness": verdict["correctness"] if verdict else None,
                     "citation_support": verdict["citation_support"] if verdict else None,
                     "invented_claims": len(verdict["invented_claims"]) if verdict else None})
    return rows


def summarize(cfg: JudgeConfig) -> dict[str, Any]:
    # Only this judge's results: results from different judges are never pooled.
    entries = [e for e in load_cache()
               if e.get("judge_model") == cfg.model and e.get("judge_provider", GEMINI) == cfg.provider]
    golden = load_golden()
    required = {q["id"]: len(q["key_facts"]) for q in golden["questions"]}
    answered = benchmark_items()
    bench = [e for e in entries if e["set"] == "benchmark"]
    check = [e for e in entries if e["set"] == "judge-check"]

    def of(metric: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [e for e in rows if e["metric"] == metric]

    def ragas_block(metric: str) -> dict[str, Any]:
        rows = of(metric, bench)
        values = [float(e["value"]) for e in rows if e["status"] == "ok"]
        return {"judged": len(rows), "mean": _mean(values), "n_scored": len(values),
                "undefined": sum(1 for e in rows if e["status"] == "undefined"),
                "parse_errors": sum(1 for e in rows if e["status"] == "parse_error")}

    rubric_rows = of(RUBRIC, bench)
    ok = [e for e in rubric_rows if e["status"] == "ok"]
    positives = [e for e in ok if e["kind"] == "positive"]
    covered = sum(len(e["verdict"]["key_facts_covered"]) for e in positives)
    needed = sum(required.get(e["question_id"], 0) for e in positives)
    rubric = {
        "judged": len(rubric_rows),
        "parse_errors": sum(1 for e in rubric_rows if e["status"] == "parse_error"),
        "answerable_judged": len(positives),
        "correctness": {str(score): sum(1 for e in positives if e["verdict"]["correctness"] == score)
                        for score in (2, 1, 0)},
        "key_facts_covered": covered, "key_facts_required": needed,
        "key_fact_recall": covered / needed if needed else None,
        "citation_support": {str(score): sum(1 for e in ok if e["verdict"]["citation_support"] == score)
                             for score in (2, 1, 0)},
        "answers_with_invented_claims": sum(1 for e in ok if e["verdict"]["invented_claims"]),
        "rows_judged_ok": len(ok),
        "negatives_answered": sum(1 for i in answered if i.kind == "negative"),
    }
    check_ok = [e for e in of(RUBRIC, check) if e["status"] == "ok"]
    judge_check: dict[str, Any] = {"judged": len(of(RUBRIC, check)),
                                   "parse_errors": sum(1 for e in of(RUBRIC, check) if e["status"] == "parse_error")}
    for kind in ("good", "omission", "invented_claim", "wrong_citation"):
        rows = [e for e in check_ok if e["kind"] == kind]
        judge_check[kind] = {"judged": len(rows), "agreeing": sum(1 for e in rows if agrees(kind, e["verdict"]))}
    runs = ([json.loads(line) for line in RUNS_LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
            if RUNS_LOG.exists() else [])
    return {
        "generated_by": "python -m eval.judge summarize",
        "protocol": "eval/answer_eval_protocol.md",
        "opinion_of": f"the judge model ({cfg.label}); not ground truth",
        "judge_provider": cfg.provider, "judge_model": cfg.model, "ragas_version": RAGAS_VERSION,
        "relevancy_strictness": RELEVANCY_STRICTNESS,
        "rubric_prompt_sha256": sha256(rubric_prompt()),
        "benchmark": {"answered_rows": len(answered), "faithfulness": ragas_block(FAITHFULNESS),
                      "answer_relevancy": ragas_block(RELEVANCY), "rubric": rubric,
                      "per_question": _per_question(answered, bench)},
        "judge_check": judge_check,
        "requests": {"runs": len(runs), "sent": sum(int(r.get("requests_sent", 0)) for r in runs),
                     "by_provider": {p: sum(int(r.get("requests_sent", 0)) for r in runs
                                            if r.get("judge_provider", GEMINI) == p) for p in PROVIDERS}},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_plan = sub.add_parser("plan", help="list what is left to judge and its request cost (no LLM)")
    p_plan.add_argument("--set", choices=SETS)
    p_run = sub.add_parser("run", help="judge pending items, within --max-requests")
    p_run.add_argument("--set", choices=SETS, required=True)
    p_run.add_argument("--max-requests", type=int, required=True,
                       help="judge requests this run may send, retries included")
    p_run.add_argument("--env-file", help="read the provider's API key from this .env into the process only")
    sub.add_parser("summarize", help=f"write {SUMMARY_JSON.relative_to(ROOT).as_posix()} from the cache")
    args = parser.parse_args(argv)
    if args.command == "plan":
        cfg = judge_config()
        result = plan([args.set] if args.set else list(SETS), cfg)
        print(json.dumps(result, indent=2))
        total = sum(v["requests_needed_without_retries"] for v in result.values())
        quota = DAILY_QUOTA[cfg.provider]
        print(f"judge: {cfg.label}. {total} request(s) left, about {math.ceil(total / quota)} day(s) at "
              f"{quota} a day (check the provider's current free limits)")
    elif args.command == "run":
        record = run(args.set, args.max_requests, args.env_file)
        return 0 if record["stopped"].startswith(("finished", "budget")) else 1
    else:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        SUMMARY_JSON.write_text(json.dumps(summarize(judge_config()), indent=2) + "\n", encoding="utf-8")
        print(f"wrote {SUMMARY_JSON.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
