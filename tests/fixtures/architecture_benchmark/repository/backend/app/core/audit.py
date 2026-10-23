import logging

log = logging.getLogger("licensing.audit")


def record_signup(username: str, password: str, email: str):
    log.info("signup username=%s password=%s email=%s", username, password, email)


def record_decision(actor_id: int, request_id: int, approved: bool):
    log.info("decision actor_id=%d request_id=%d approved=%s", actor_id, request_id, approved)
