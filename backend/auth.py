import hmac

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import API_KEY

bearer_scheme = HTTPBearer(auto_error=False)


def check_api_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    """Swagger accepts a bearer token; enter the key without typing 'Bearer '."""
    if not API_KEY:  # no key configured: local mode, skip the check
        return
    if credentials is None or not hmac.compare_digest(credentials.credentials, API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )