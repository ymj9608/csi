ROWS = {}
def save(member):
    value = dict(member, id=len(ROWS)+1)
    ROWS[value['id']] = value
    return dict(value)
