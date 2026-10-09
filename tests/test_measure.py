"""The retrieval metrics and the keep-a-component decision rule."""
import pytest

from eval.measure import decide, paired_bootstrap, question_metrics


def test_question_metrics():
    ranked = [("a", 0), ("b", 1), ("a", 2), ("c", 0)]
    relevant = {("a", 2), ("c", 0), ("z", 9)}
    m = question_metrics(ranked, relevant)
    assert m["recall@1"] == 0.0
    assert m["recall@5"] == pytest.approx(2 / 3) and m["recall@10"] == pytest.approx(2 / 3)
    assert m["mrr@10"] == pytest.approx(1 / 3)  # first relevant at rank 3
    assert question_metrics([("x", 0)], {("y", 0)})["mrr@10"] == 0.0


def test_paired_bootstrap_detects_a_consistent_gain_and_not_noise():
    gain = paired_bootstrap([0.5] * 30, [0.6] * 30)
    assert gain["mean_diff"] == pytest.approx(0.1) and gain["ci_low"] > 0
    noise = paired_bootstrap([0.0, 1.0] * 15, [1.0, 0.0] * 15)
    assert noise["ci_low"] < 0 < noise["ci_high"]
    assert paired_bootstrap([0.1, 0.9], [0.2, 0.4]) == paired_bootstrap([0.1, 0.9], [0.2, 0.4])  # fixed seed


def _cmp(diff, low):
    return {"mean_diff": diff, "ci_low": low, "ci_high": diff + 0.1}


@pytest.mark.parametrize("fusion, rerank, chosen", [
    (_cmp(0.05, 0.01), _cmp(0.05, 0.01), "hybrid+rerank"),
    (_cmp(0.05, 0.01), _cmp(0.05, -0.01), "hybrid"),       # reranker gain not reliable
    (_cmp(0.01, 0.001), _cmp(0.0, -0.02), "vector"),       # fusion gain below the 0.02 bar
])
def test_decision_rule(fusion, rerank, chosen):
    decision = decide({}, {"hybrid vs vector": fusion, "hybrid+rerank vs hybrid": rerank}, "vector")
    assert decision["chosen"] == chosen


def test_output_paths_default_to_committed_results_and_accept_a_prefix(tmp_path):
    from eval import measure

    assert measure.output_paths(None) == (measure.RESULTS_JSON, measure.RESULTS_MD)
    json_path, md_path = measure.output_paths(str(tmp_path / "retrieval_rerun"))
    assert json_path == tmp_path / "retrieval_rerun.json"
    assert md_path == tmp_path / "retrieval_rerun.md"
