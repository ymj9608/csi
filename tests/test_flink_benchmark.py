"""Keep benchmark evidence grading honest; no network/model calls."""
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark_flink import evaluate
from benchmark_flink_models import score, OUT


def test_labeled_metrics_do_not_count_unrelated_findings_as_false_positives():
    labels = [{'id': 'V', 'path': 'A.java', 'startLine': 2, 'endLine': 2, 'positive': True},
              {'id': 'N', 'path': 'A.java', 'startLine': 5, 'endLine': 5, 'positive': False}]
    findings = [{'filePath': 'A.java', 'startLine': 2, 'endLine': 2},
                {'filePath': 'unknown.java', 'startLine': 3, 'endLine': 3}]
    q = evaluate(findings, labels)
    assert q['truePositive'] == 1 and q['falsePositive'] == 0


def test_negative_control_is_not_a_true_positive():
    q = evaluate([{'filePath': 'A.java', 'startLine': 5, 'endLine': 5}],
        [{'id': 'V', 'path': 'A.java', 'startLine': 2, 'endLine': 2, 'positive': True},
         {'id': 'N', 'path': 'A.java', 'startLine': 5, 'endLine': 5, 'positive': False}])
    assert q['falsePositive'] == 1 and q['recall'] == 0


def test_failed_model_call_is_not_a_zero_quality_completed_trial():
    assert score({'complete': False}, [], 'mutated') is None


def test_invalid_citation_and_wrong_path_never_become_verified_findings():
    labels = '[{"id":"V1","path":"A.java","startLine":1,"endLine":1,"positive":true}]'
    response = {'complete': True, 'answer': {'findings': [
        {'filePath': 'A.java', 'line': 1, 'evidence': 'invented quote'},
        {'filePath': 'B.java', 'line': 1, 'evidence': 'LOG.info(password);'}]}}
    with patch.object(Path, 'read_text', return_value=labels), patch(
            'benchmark_flink_models.source', return_value=b'LOG.info(password);\n'):
        q = score(response, ['A.java'], 'mutated')
    assert q['sourceVerifiedFindings'] == 0 and q['invalidEvidenceCount'] == 2
    assert q['truePositiveIds'] == []


def test_exact_file_line_and_quote_can_be_verified():
    labels = '[{"id":"V1","path":"A.java","startLine":1,"endLine":1,"positive":true}]'
    response = {'complete': True, 'answer': {'findings': [
        {'filePath': 'A.java', 'line': 1, 'evidence': 'LOG.info(password);'}]}}
    with patch.object(Path, 'read_text', return_value=labels), patch(
            'benchmark_flink_models.source', return_value=b'LOG.info(password);\n'):
        q = score(response, ['A.java'], 'mutated')
    assert q['truePositiveIds'] == ['V1'] and q['invalidEvidenceCount'] == 0
