import hashlib


def document_checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def same_document(content: bytes, expected_checksum: str) -> bool:
    return document_checksum(content) == expected_checksum
