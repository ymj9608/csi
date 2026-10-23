"""Validate VLM extraction results before they're trusted as EXTRACTED.

Deliberately coarse: a component is a name, a role, an isolation guess,
and a confidence state. No file paths, no code structure — a VLM reading
an image cannot know either, and this project does not ask it to guess.
"""
ISOLATION_STATUSES = {"ISOLATED", "PRODUCTION", "UNKNOWN"}
STATES = {"OBSERVED", "INFERRED", "UNKNOWN"}


def validate_result(raw):
    if not isinstance(raw, dict):
        raise ValueError("Result must be an object")
    summary = raw.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("Missing summary")
    components = raw.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("Missing components")
    cleaned = []
    for component in components:
        if not isinstance(component, dict):
            raise ValueError("Component must be an object")
        name = component.get("name")
        role = component.get("role")
        isolation_status = component.get("isolationStatus")
        state = component.get("state")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Missing component name")
        if not isinstance(role, str) or not role.strip():
            raise ValueError("Missing component role")
        if isolation_status not in ISOLATION_STATUSES:
            raise ValueError("Invalid isolationStatus")
        if state not in STATES:
            raise ValueError("Invalid state")
        cleaned.append({"name": name, "role": role, "isolationStatus": isolation_status, "state": state})
    return {"components": cleaned, "summary": summary}
