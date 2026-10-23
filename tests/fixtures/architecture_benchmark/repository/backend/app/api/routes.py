from app.core.errors import AccessDenied
from app.schemas.dto import Signup, SearchQuery
from app.services.accounts import register, authenticate
from app.services.requests import create_request, decide_request
from app.repositories.users import search_users
from app.repositories.catalog import list_licenses
from app.services.dashboard import summary


class Routes:
    def __init__(self, db):
        self.db = db

    def signup(self, body):
        payload = Signup.from_mapping(body)
        return register(self.db, payload)

    def login(self, body):
        return authenticate(self.db, body["username"], body["password"])

    def directory(self, actor, query):
        if not actor or actor["role"] != "MASTER":
            raise AccessDenied("Directory is restricted to administrators")
        return search_users(self.db, SearchQuery(query).text)

    def licenses(self, actor, query=""):
        if not actor:
            raise AccessDenied("Sign in first")
        return list_licenses(self.db, SearchQuery(query).text)

    def request_license(self, actor, license_id, reason):
        if not actor:
            raise AccessDenied("Sign in first")
        return create_request(self.db, actor, license_id, reason)

    def decide(self, actor, request_id, approved):
        if not actor or actor["role"] != "MASTER":
            raise AccessDenied("Only administrators may decide requests")
        return decide_request(self.db, actor, request_id, approved)

    def dashboard(self, actor):
        if not actor:
            raise AccessDenied("Sign in first")
        return summary(self.db, actor["id"])
