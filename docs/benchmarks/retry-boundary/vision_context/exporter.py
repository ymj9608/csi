import json
from pathlib import Path
from copy import deepcopy
from storage import OBSERVABILITY
CONFIG = json.loads(Path('topology.json').read_text())

def forward(envelope):
    OBSERVABILITY.append({'destination': CONFIG['archive_export']['destination'], 'payload': deepcopy(envelope)})
