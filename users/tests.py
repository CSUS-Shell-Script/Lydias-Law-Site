from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from users.models import User


class LoginErrorMessagingTests(TestCase):
    def _messages(self, response):
        return [m.message for m in get_messages(response.wsgi_request)]

    def test_client_login_unknown_email_shows_invalid_email(self):
        url = reverse("login")
        resp = self.client.post(
            url,
            data={"email": "missing@example.com", "password": "pw", "role": "client"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Invalid email.", self._messages(resp))

    def test_client_login_wrong_password_shows_invalid_password(self):
        User.objects.create_user(
            email="client@example.com",
            password="correctpw",
            first_name="Client",
            last_name="User",
            is_staff=False,
            is_active=True,
        )
        url = reverse("login")
        resp = self.client.post(
            url,
            data={"email": "client@example.com", "password": "wrongpw", "role": "client"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Invalid password.", self._messages(resp))

    def test_admin_login_unknown_email_shows_invalid_email(self):
        url = reverse("login")
        resp = self.client.post(
            url,
            data={"email": "missing-admin@example.com", "password": "pw", "role": "admin"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Invalid email.", self._messages(resp))

    def test_admin_login_non_admin_email_shows_invalid_email(self):
        User.objects.create_user(
            email="client@example.com",
            password="pw",
            first_name="Client",
            last_name="User",
            is_staff=False,
            is_active=True,
        )
        url = reverse("login")
        resp = self.client.post(
            url,
            data={"email": "client@example.com", "password": "pw", "role": "admin"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Invalid email.", self._messages(resp))
