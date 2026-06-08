from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from services.auth_service import AuthenticatedUser, GoogleOAuthConfig

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


@dataclass(frozen=True)
class GoogleTokenSet:
    access_token: str
    refresh_token: str = ""
    expires_in: int = 0
    token_type: str = "Bearer"
    scope: str = ""


def exchange_auth_code(config: GoogleOAuthConfig, client_secret: str, auth_code: str) -> GoogleTokenSet:
    if not client_secret:
        raise ValueError("Google OAuth client_secret is required.")
    if not auth_code:
        raise ValueError("Google OAuth authorization code is required.")
    payload = {
        "code": auth_code,
        "client_id": config.client_id,
        "client_secret": client_secret,
        "redirect_uri": config.redirect_uri,
        "grant_type": "authorization_code",
    }
    data = _post_form(GOOGLE_TOKEN_URL, payload)
    return GoogleTokenSet(
        access_token=str(data.get("access_token", "")),
        refresh_token=str(data.get("refresh_token", "")),
        expires_in=int(data.get("expires_in", 0) or 0),
        token_type=str(data.get("token_type", "Bearer")),
        scope=str(data.get("scope", "")),
    )


def fetch_google_user(access_token: str) -> AuthenticatedUser:
    if not access_token:
        raise ValueError("Google OAuth access token is required.")
    request = Request(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}, method="GET")
    try:
        with urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Google userinfo error {error.code}: {detail}") from error
    return AuthenticatedUser(
        google_sub=str(data.get("sub", "")),
        email=str(data.get("email", "")),
        display_name=str(data.get("name", "")),
    )


def _post_form(url: str, payload: dict[str, str]) -> dict:
    body = urlencode(payload).encode("utf-8")
    request = Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Google OAuth error {error.code}: {detail}") from error
