from repository import save
from events import member_created
from dispatcher import publish

def signup(payload):
    member = save({'name': payload['name']})
    publish(member_created(member))
    return {'id': member['id']}
