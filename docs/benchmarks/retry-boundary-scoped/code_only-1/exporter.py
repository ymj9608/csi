import json
from pathlib import Path
from copy import deepcopy
from storage import OBSERVABILITY
CONFIG = json.loads(Path('topology.json').read_text())

def forward(envelope):
    # Extract phone data and mask it for external destinations
    payload = deepcopy(envelope)
    if 'event' in payload:
        event = payload['event']
        if 'member' in event and 'phone' in event['member']:
            event['member']['phone'] = "[PHONE_REDACTED]"

    # Preserve original structure for internal replay/retries
    OBSERVABILITY.append({
        'destination': CONFIG['archive_export']['destination'],
        'payload': payload
    })
