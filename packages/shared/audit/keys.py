from hashlib import sha256


def ordinal_key(path: str) -> str:
    return "".join(c.upper() if len(c.upper()) == 1 else c for c in path.replace("/", "\\"))


def path_key(path: str | None) -> str | None:
    return sha256(ordinal_key(path).encode()).hexdigest() if path is not None else None
