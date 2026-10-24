import pytest
from coding_agent.runtime_settings import integer, load_environment, JOB_SECONDS, EXECUTION_SECONDS, ORCHESTRATION_SECONDS


def test_environment_file_settings_respect_process_override(monkeypatch):
    monkeypatch.delenv('CSI_LOCAL_VLM_TIMEOUT_SECONDS', raising=False)
    monkeypatch.setenv('CSI_ARCHITECTURE_TIMEOUT_SECONDS', '1000')
    load_environment({'CSI_LOCAL_VLM_TIMEOUT_SECONDS':'700', 'CSI_ARCHITECTURE_TIMEOUT_SECONDS':'900'})
    assert integer('CSI_LOCAL_VLM_TIMEOUT_SECONDS',600,30,900) == 700
    assert integer('CSI_ARCHITECTURE_TIMEOUT_SECONDS',900,60,1800) == 1000


@pytest.mark.parametrize('value', ['0', '-1', '901', 'invalid'])
def test_invalid_limits_do_not_disable_timeouts(monkeypatch, value):
    monkeypatch.setenv('CSI_LOCAL_VLM_TIMEOUT_SECONDS', value)
    with pytest.raises(ValueError, match='CSI_LOCAL_VLM_TIMEOUT_SECONDS'):
        integer('CSI_LOCAL_VLM_TIMEOUT_SECONDS',600,30,900)


def test_execution_leaves_delivery_margin_inside_lease():
    assert ORCHESTRATION_SECONDS < EXECUTION_SECONDS <= JOB_SECONDS - 60
