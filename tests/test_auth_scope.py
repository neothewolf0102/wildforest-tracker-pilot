from __future__ import annotations

import unittest

from services.auth_service import GOOGLE_DRIVE_FILE_SCOPE, GoogleOAuthConfig, build_google_login_url, validate_minimum_drive_scope


class AuthScopeTest(unittest.TestCase):
    def test_google_login_url_uses_minimum_drive_scope(self) -> None:
        config = GoogleOAuthConfig(client_id="client", redirect_uri="https://example.com")
        url = build_google_login_url(config, state="state-token")
        self.assertIn("client_id=client", url)
        self.assertIn("response_type=code", url)
        self.assertTrue(validate_minimum_drive_scope(config.scopes))
        self.assertIn("drive.file", url)

    def test_full_drive_scope_is_not_required(self) -> None:
        self.assertEqual(GOOGLE_DRIVE_FILE_SCOPE, "https://www.googleapis.com/auth/drive.file")


if __name__ == "__main__":
    unittest.main()
