"""Portable execution budgets, independent of repository and operating system."""
import os

JOB_SECONDS = 2700  # Must match the backend lease; retain 60 seconds for delivery.
EXECUTION_SECONDS = JOB_SECONDS - 60
ORCHESTRATION_SECONDS = 2100


def integer(name, default, minimum, maximum):
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        raise ValueError(f'Invalid {name}: expected an integer') from None
    if not minimum <= value <= maximum:
        raise ValueError(f'Invalid {name}: expected {minimum}..{maximum}')
    return value


def load_environment(values):
    for name in ('CSI_LOCAL_VLM_TIMEOUT_SECONDS', 'CSI_LOCAL_VLM_NUM_CTX',
                 'CSI_LOCAL_VLM_NUM_PREDICT', 'CSI_LOCAL_VLM_KEEP_ALIVE_SECONDS',
                 'CSI_ARCHITECTURE_TIMEOUT_SECONDS', 'CSI_ARCHITECTURE_NUM_PREDICT'):
        if values.get(name) and name not in os.environ:
            os.environ[name] = values[name]
