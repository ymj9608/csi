from dataclasses import dataclass
from app.core.errors import InvalidInput


@dataclass(frozen=True)
class Signup:
    username: str
    name: str
    email: str
    phone: str
    password: str

    @classmethod
    def from_mapping(cls, data):
        keys = ("username", "name", "email", "phone", "password")
        if any(not isinstance(data.get(key), str) for key in keys):
            raise InvalidInput("All signup fields must be strings")
        if not 3 <= len(data["username"]) <= 40:
            raise InvalidInput("Username length must be between 3 and 40")
        if not 12 <= len(data["password"]) <= 128:
            raise InvalidInput("Password length must be between 12 and 128")
        if "@" not in data["email"] or len(data["email"]) > 254:
            raise InvalidInput("Invalid email")
        if not 1 <= len(data["name"]) <= 80 or len(data["phone"]) > 30:
            raise InvalidInput("Invalid contact information")
        return cls(**{key: data[key] for key in keys})


@dataclass(frozen=True)
class SearchQuery:
    text: str

    def __post_init__(self):
        if not isinstance(self.text, str) or len(self.text) > 150:
            raise InvalidInput("Search query must be at most 150 characters")
