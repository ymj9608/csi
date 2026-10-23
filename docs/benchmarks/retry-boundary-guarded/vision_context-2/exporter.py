import json
from pathlib import Path
from copy import deepcopy
from storage import OBSERVABILITY
CONFIG = json.loads(Path('topology.json').read_text())

def forward(envelope):
    if not (envelope['event']['kind'] == 'registered' and 'phone' in envelope.get('event', {}).get('member', {}) and 
            CONFIG['archive_export']['zone'] != 'external' or CONFIG['archive_export']['phoneAllowed'] is False):
        OBSERVABILITY.append({'destination': CONFIG['archive_export']['destination'], 'payload': deepcopy(envelope)})
