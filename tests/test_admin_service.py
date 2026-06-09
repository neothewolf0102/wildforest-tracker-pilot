from __future__ import annotations

import unittest

from services import admin_service


class FakeStore:
    def __init__(self) -> None:
        self.files: dict[str, object] = {}

    def load_json(self, filename: str, default=None):
        return self.files.get(filename, default)

    def save_json(self, filename: str, data) -> None:
        self.files[filename] = data


class AdminServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        if hasattr(admin_service._admin_state, "clear"):
            admin_service._admin_state.clear()
        self.store = FakeStore()
        admin_service.configure_access_config((admin_service.SUPER_ADMIN_EMAIL,), (admin_service.SUPER_ADMIN_EMAIL, "pilot@example.com"))
        admin_service.configure_admin_store(self.store)

    def test_not_allowlisted_user_is_blocked_with_required_message(self) -> None:
        decision = admin_service.get_access_decision("unknown@example.com")
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reason"], "not_allowlisted")
        self.assertEqual(decision["message"], admin_service.NOT_INVITED_MESSAGE)

    def test_disabled_user_is_blocked_with_required_message(self) -> None:
        admin_service.set_email_access("pilot@example.com", False, "test disable")
        decision = admin_service.get_access_decision("pilot@example.com")
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reason"], "disabled")
        self.assertEqual(decision["message"], admin_service.DISABLED_MESSAGE)

    def test_super_admin_is_always_allowed(self) -> None:
        admin_service.set_email_access(admin_service.SUPER_ADMIN_EMAIL, False, "cannot disable owner")
        decision = admin_service.get_access_decision(admin_service.SUPER_ADMIN_EMAIL)
        self.assertTrue(decision["allowed"])

    def test_suspicious_level_planner_frequency_creates_flag(self) -> None:
        for _ in range(21):
            admin_service.log_activity("pilot@example.com", "Level Planner", "level_planner_calculated")
        flags = admin_service.get_suspicious_flags()
        self.assertTrue(any(flag["user_email"] == "pilot@example.com" for flag in flags))
        self.assertTrue(any(item["title"] == "user_suspicious_behavior_flagged" for item in admin_service.get_notifications()))

    def test_notifications_can_be_marked_read(self) -> None:
        notification = admin_service.create_notification("info", "new_user_added_to_allowlist", "Added", "pilot@example.com")
        self.assertTrue(admin_service.mark_notification_read(notification["id"]))
        self.assertTrue(next(item for item in admin_service.get_notifications() if item["id"] == notification["id"])["read"])
        admin_service.create_notification("warning", "repeated_validation_failed", "Warning", "pilot@example.com")
        admin_service.mark_all_notifications_read()
        self.assertTrue(all(item["read"] for item in admin_service.get_notifications()))


if __name__ == "__main__":
    unittest.main()
