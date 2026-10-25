import json
from pathlib import Path
from copy import deepcopy
from storage import OBSERVABILITY
CONFIG = json.loads(Path('topology.json').read_text())

def forward(envelope):
    payload_copy = deepcopy(envelope)
    if CONFIG['archive_export']['zone'] == 'external':
        # Remove phone from external destination only
        if 'event' in payload_copy and 'member' in payload_copy['event']:
            payload_copy['event']['member'].pop('phone', None)
    OBSERVABILITY.append({'destination': CONFIG['archive_export']['destination'], 'payload': payload_copy})
