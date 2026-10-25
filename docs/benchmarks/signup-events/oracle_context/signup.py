import re
from repository import save
from events import member_created
from dispatcher import publish

_PHONE_RE = re.compile(r'^010[0-9]{8}$')


def _validate_phone(phone):
    if phone is None:
        return None
    if not isinstance(phone, str) or not _PHONE_RE.fullmatch(phone):
        raise ValueError('invalid phone')
    return phone


def signup(payload):
    phone = _validate_phone(payload.get('phone'))
    member = save({'name': payload['name'], 'phone': phone})
    publish(member_created(member))
    return {'id': member['id']}
