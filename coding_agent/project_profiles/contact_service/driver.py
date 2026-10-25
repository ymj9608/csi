"""Independent Python layout and callable; same privacy pack and common engine."""
from contacts.service import add_contact


def exercise(request, caplog):
    records = []
    with caplog.at_level('INFO', logger='contact.audit'):
        value = add_contact(records, 'fixture@example.com', '+82-000-5555')
    rejected = False
    try:
        add_contact(records, '', '+82-000-5555')
    except ValueError:
        rejected = True
    return {'sensitiveValues':['fixture@example.com', '+82-000-5555'], 'logs':caplog.text,
            'usefulEvent':'CONTACT_STORED', 'behaviorPreserved':value == 1 and records == [
                {'email':'fixture@example.com','phone':'+82-000-5555'}], 'invalidRejected':rejected}
