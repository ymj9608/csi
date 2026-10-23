from repository import save
from events import member_created
from dispatcher import publish
import re

def validate_phone(phone):
    """Validate phone number format: ASCII '010' followed by eight digits."""
    if not isinstance(phone, str) or len(phone) != 11:
        return False
    return bool(re.fullmatch(r'^010\d{8}$', phone))

def signup(payload):
    # Validate and process phone number if provided
    phone = payload.get('phone')
    if phone is not None:
        if not validate_phone(phone):
            raise ValueError("Phone must be ASCII '010' followed by eight digits.")
    
    member = save({'name': payload['name'], 'phone': phone})
    publish(member_created(member))
    return {'id': member['id']}
