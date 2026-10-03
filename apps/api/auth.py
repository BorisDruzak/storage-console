import hashlib
from typing import Annotated

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

collector_scheme = HTTPBearer(auto_error=False, scheme_name="CollectorToken")


def token_hash(token: str) -> str:
    return hashlib.sha256(("collector:" + token).encode()).hexdigest()


def collector_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(collector_scheme)],
) -> str:
    if credentials is None or not 32 <= len(credentials.credentials) <= 512:
        raise HTTPException(
            401, detail="COLLECTOR_AUTH_REQUIRED", headers={"WWW-Authenticate": "Bearer"}
        )
    return credentials.credentials
