from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()

# Create your tests here.

# *** 403 Permission Denied Tests ***
class AdminPermissionTests(TestCase):
    # Setup different user types
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
    # Test for guest user -> not logged in 
    # Should get 403 page
    def test_guest_user_gets_403(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 403)
        
    # Test for client user -> logged in
    # Should get 403 page
    def test_client_user_gets_403(self):
        self.client.login(email="client@unitTest.com", password="Password1!")
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 403)

    # Test for admin user -> logged in
    # Should NOT get 403 page
    def test_superuser_gets_200(self):
        self.client.login(email="admin@unitTest.com", password="Pass12345!")
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "admin/dashboard.html")

    # Tests if custom 403 template is rendered instead of Django default
    def test_403_uses_custom_tempate(self):
        self.client.login(email="client@unitTest.com", password="Password1!")
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 403)
        self.assertTemplateUsed(resp, "403.html")