def public_profile(record):
    result = dict(record)
    result.pop('phone', None)
    result.pop('email', None)
    return result