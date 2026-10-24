"""pii-log-leak-v1: project behavior supplied by a reviewed, pinned CSI driver."""
import csi_project_driver


def exercise(request, caplog):
    result = csi_project_driver.exercise(request, caplog)
    assert set(result) == {'sensitiveValues', 'logs', 'usefulEvent', 'behaviorPreserved', 'invalidRejected'}
    assert result['sensitiveValues'] and all(isinstance(v, str) and v for v in result['sensitiveValues'])
    return result


def test_no_sensitive_logs(request, caplog):
    value = exercise(request, caplog)
    assert all(secret not in value['logs'] for secret in value['sensitiveValues'])


def test_useful_log_preserved(request, caplog):
    value = exercise(request, caplog)
    assert value['usefulEvent'] and value['usefulEvent'] in value['logs']


def test_behavior_preserved(request, caplog):
    assert exercise(request, caplog)['behaviorPreserved'] is True


def test_invalid_input_rejected(request, caplog):
    assert exercise(request, caplog)['invalidRejected'] is True
