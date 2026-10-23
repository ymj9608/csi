def member_created(member):
    """Preserve one member_created event per subscriber with member.id, existing alias name and legacy signup."""
    event = {
        'type': 'member_created', 
        'member': {
            'id': member['id'],
            'name': member.get('name')
        }
    }
    return event