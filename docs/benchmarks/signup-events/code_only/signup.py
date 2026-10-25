from repository import save
from events import member_created
from dispatcher import publish


def _validate_phone(phone):
    if phone is None:
        return None
    if not isinstance(phone, str) or len(phone) != 11 or not phone.startswith('010') or not phone[3:].isdigit():
        raise ValueError('invalid phone')
    return phone


def signup(payload):
    phone = _validate_phone(payload.get('phone'))
    member = {'name': payload['name']}
    if phone is not None:
        member['phone'] = phone
    member = save(member)
    publish(member_created(member))
    return {'id': member['id']}
