from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

GOOGLE_OAUTH_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"
OPENID_SCOPES = ("openid", "email", "profile")
WILDFOREST_DRIVE_FOLDER_NAME = "Wildforest Tracker"


@dataclass(frozen=True)
class GoogleOAuthConfig:
    client_id: str
    redirect_uri: str
    scopes: tuple[str, ...] = (*OPENID_SCOPES, GOOGLE_DRIVE_FILE_SCOPE)


@dataclass(frozen=True)
class AuthenticatedUser:
    google_sub: str
    email: str
    display_name: str = ""

    @property
    def user_id(self) -> str:
        return f"google_{self.google_sub}"


def build_google_login_url(config: GoogleOAuthConfig, state: str, prompt: str = "consent") -> str:
    if not config.client_id:
        raise ValueError("Google OAuth client_id is required.")
    if not config.redirect_uri:
        raise ValueError("Google OAuth redirect_uri is required.")
    if not state:
        raise ValueError("OAuth state is required.")
    query = {
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "response_type": "code",
        "scope": " ".join(config.scopes),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": prompt,
        "state": state,
    }
    return f"{GOOGLE_OAUTH_AUTHORIZE_URL}?{urlencode(query)}"


def validate_minimum_drive_scope(scopes: tuple[str, ...] | list[str]) -> bool:
    return GOOGLE_DRIVE_FILE_SCOPE in set(scopes)
