import json
from pathlib import Path
from copy import deepcopy
from storage import OBSERVABILITY
CONFIG = json.loads(Path('topology.json').read_text())

def forward(envelope):
    payload_copy = deepcopy(envelope['payload']) if 'payload' in envelope else deepcopy(envelope)
    if CONFIG['archive_export']['phoneAllowed'] is False:
        if isinstance(payload_copy, dict) and 'event' in payload_copy:
            event_copy = deepcopy(payload_copy['event'])
            if 'member' in event_copy and 'phone' in event_copy['member']:
                del event_copy['member']['phone']
            payload_copy['event'] = event_copy
    OBSERVABILITY.append({'destination': CONFIG['archive_export']['destination'], 'payload': payload_copy})
