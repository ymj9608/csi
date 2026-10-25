import json
from pathlib import Path
from copy import deepcopy
from storage import OBSERVABILITY
CONFIG = json.loads(Path('topology.json').read_text())

def forward(envelope):
    # Filter out phone data for external destinations
    filtered_payload = {
        'event': envelope['payload']['event'],
        'error': envelope.get('error'),
        'attempts': envelope.get('attempts')
    }
    OBSERVABILITY.append({
        'destination': CONFIG['archive_export']['destination'], 
        'payload': filtered_payload
    })
