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


class AdminPermissionTests(TestCase):
    def setUp(self):
        self.url = "/administrator/dashboard/"

        self.normal_user = User.objects.create_user(
            email="client@unitTest.com",
            password="Password1!"
        )
        self.superuser = User.objects.create_superuser(
            email="admin@unitTest.com",
            password="Pass12345!"
        )

    def test_guest_user_gets_403(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 403)

    def test_client_user_gets_403(self):
        self.client.login(email="client@unitTest.com", password="Password1!")
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 403)

    def test_superuser_gets_200(self):
        self.client.login(email="admin@unitTest.com", password="Pass12345!")
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "admin/dashboard.html")

    def test_403_uses_custom_template(self):
        self.client.login(email="client@unitTest.com", password="Password1!")
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 403)
        self.assertTemplateUsed(resp, "403.html")
