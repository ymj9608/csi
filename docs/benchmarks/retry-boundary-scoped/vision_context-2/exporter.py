import json
from pathlib import Path
from copy import deepcopy
from storage import OBSERVABILITY
CONFIG = json.loads(Path('topology.json').read_text())

def forward(envelope):
    # Preserve event id, error and attempts for external diagnostics
    filtered_payload = {
        'event': envelope['payload']['event'],
        'error': envelope.get('error', None),
        'attempts': envelope.get('attempts', 0)
    }
    OBSERVABILITY.append({
        'destination': CONFIG['archive_export']['destination'],
        'payload': filtered_payload
    })
