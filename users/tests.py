from django.contrib.messages import get_messages
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model

from users.models import User

User = get_user_model()

class LoginErrorMessagingTests(TestCase):
    def setUp(self):
        site = Site.objects.get_or_create(id=1, defaults={"name": "Test Site", "domain": "testserver"})[0]
        social_app, _ = SocialApp.objects.get_or_create(
            provider="google",
            defaults={"name": "Google (test)", "client_id": "test-client-id"},
        )
        social_app.sites.add(site)
        
    def _messages(self, response):
        return [m.message for m in get_messages(response.wsgi_request)]

    def test_login_unknown_email_shows_user_does_not_exist_404(self):
        url = reverse("login")
        resp = self.client.post(url, data={"email": "missing@example.com", "password": "pw"}, follow=True)
        self.assertEqual(resp.status_code, 404)
        self.assertIn("User does not exist, please create an account to login.", self._messages(resp))

    def test_login_wrong_password_shows_did_not_match_401(self):
        User.objects.create_user(
            email="client@example.com",
            password="correctpw",
            first_name="Client",
            last_name="User",
            is_staff=False,
            is_active=True,
        )
        url = reverse("login")
        resp = self.client.post(url, data={"email": "client@example.com", "password": "wrongpw"}, follow=True)
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Your email and password did not match, please try again.", self._messages(resp))


class LoginTests(TestCase):
    """Test user login functionality and error messages"""

    def setUp(self):
        """Set up test client and test users"""
        self.client = Client()
        self.login_url = reverse("login")
        
        # Create a minimal SocialApp to prevent allauth template tag errors during login.html rendering
        site = Site.objects.get_or_create(id=1, defaults={"name": "Test Site", "domain": "testserver"})[0]
        social_app, created = SocialApp.objects.get_or_create(
            provider='google',
            defaults={
                'name': 'Google (test)',
                'client_id': 'test-client-id'
            }
        )
        # Associate the social app with the site
        social_app.sites.add(site)
        
        # Create a test user with valid email and verified account
        self.test_user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
            is_active=True  # User must be active to login
        )
        
        # Verify the email address (required for login)
        EmailAddress.objects.create(
            user=self.test_user,
            email="test@example.com",
            verified=True,
            primary=True
        )

    def test_login_with_valid_email_and_password(self):
        """
        Test that a user can log in with valid email and password
        """
        print("\nTEST: Login with valid email (test@example.com) and password (testpass123)")
        print("EXPECTED: User successfully authenticated, status=200")
        
        post_data = {
            "email": "test@example.com",
            "password": "testpass123"
        }

        response = self.client.post(self.login_url, post_data, follow=True)
        is_authenticated = response.wsgi_request.user.is_authenticated
        print(f"ACTUAL: User authenticated = {is_authenticated}, user.email = {response.wsgi_request.user.email if is_authenticated else 'N/A'}")
        
        # Check that user is authenticated and redirected successfully
        self.assertTrue(is_authenticated)
        print("Assertion 1 PASS: user is authenticated")

    def test_login_shows_error_for_nonexistent_email(self):
        """
        Test that login shows error when email doesn't exist in database
        """
        print("\nTEST: Login with nonexistent email (nonexistent@example.com)")
        print("EXPECTED: Login fails with specific error message, status=404, user not authenticated")
        
        post_data = {
            "email": "nonexistent@example.com",
            "password": "testpass123"
        }

        response = self.client.post(self.login_url, post_data, follow=True)
        messages_list = list(get_messages(response.wsgi_request))
        actual_message = str(messages_list[0]) if messages_list else "No message"
        is_authenticated = response.wsgi_request.user.is_authenticated
        status_code = response.status_code
        print(f"ACTUAL: status={status_code}, authenticated={is_authenticated}, message='{actual_message}'")
        
        # Check that user is NOT authenticated
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        print("Assertion 1 PASS: user is not authenticated")
        # Check that error message is displayed
        self.assertEqual(len(messages_list), 1)
        print("Assertion 2 PASS: exactly 1 error message displayed")
        self.assertEqual(actual_message, "User does not exist, please create an account to login.")
        print("Assertion 3 PASS: error message matches expected")
        
        # Check response status code indicates an error (404 for not found)
        self.assertEqual(response.status_code, 404)
        print("Assertion 4 PASS: response.status_code == 404")

    def test_login_shows_error_for_incorrect_password(self):
        """
        Test that login shows error when password is incorrect for existing user
        """
        print("\nTEST: Login with correct email (test@example.com) but incorrect password (wrongpassword)")
        print("EXPECTED: Login fails with specific error message, status=401, user not authenticated")
        
        post_data = {
            "email": "test@example.com",
            "password": "wrongpassword"
        }

        response = self.client.post(self.login_url, post_data, follow=True)
        messages_list = list(get_messages(response.wsgi_request))
        actual_message = str(messages_list[0]) if messages_list else "No message"
        is_authenticated = response.wsgi_request.user.is_authenticated
        status_code = response.status_code
        print(f"ACTUAL: status={status_code}, authenticated={is_authenticated}, message='{actual_message}'")
        
        # Check that user is NOT authenticated
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        print("Assertion 1 PASS: user is not authenticated")
        
        # Check that error message is displayed
        self.assertEqual(len(messages_list), 1)
        print("Assertion 2 PASS: exactly 1 error message displayed")
        self.assertEqual(
            actual_message,
            "Your email and password did not match, please try again."
        )
        print("Assertion 3 PASS: error message matches expected")
        
        # Check response status code indicates an error (401 for unauthorized)
        self.assertEqual(response.status_code, 401)
        print("Assertion 4 PASS: response.status_code == 401")

    def test_login_shows_error_for_unverified_email(self):
        """
        Test that login shows error when user's email is not verified
        """
        # Create a user with unverified email (is_active=False until email is verified)
        unverified_user = User.objects.create_user(
            email="unverified@example.com",
            password="userpass123",
            first_name="Unverified",
            last_name="User",
            is_active=False  # Unverified users cannot log in
        )
        # Create EmailAddress but mark as not verified
        EmailAddress.objects.create(
            user=unverified_user,
            email="unverified@example.com",
            verified=False,
            primary=True
        )
        
        print("\nTEST: Login with unverified email (unverified@example.com)")
        print("EXPECTED: Login fails since user is inactive, status=401, user not authenticated")
        
        post_data = {
            "email": "unverified@example.com",
            "password": "userpass123"
        }

        response = self.client.post(self.login_url, post_data, follow=True)
        messages_list = list(get_messages(response.wsgi_request))
        actual_message = str(messages_list[0]) if messages_list else "No message"
        is_authenticated = response.wsgi_request.user.is_authenticated
        status_code = response.status_code
        print(f"ACTUAL: status={status_code}, authenticated={is_authenticated}, message='{actual_message}'")
        
        # Check that user is NOT authenticated
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        print("Assertion 1 PASS: user is not authenticated")
        
        # Check that error message is displayed
        # Note: When user is inactive, Django's authenticate() returns None,
        # so the view shows the "did not match" message instead of the explicit verification message
        self.assertEqual(len(messages_list), 1)
        print("Assertion 2 PASS: exactly 1 error message displayed")
        self.assertEqual(
            actual_message,
            "Your email and password did not match, please try again."
        )
        print("Assertion 3 PASS: error message matches expected")
        
        # Check response status code indicates an error (401 for unauthorized)
        self.assertEqual(response.status_code, 401)
        print("Assertion 4 PASS: response.status_code == 401")


class SignupTests(TestCase):
    """Test user signup functionality and error messages"""

    def setUp(self):
        """Set up test client and create a site for social auth"""
        self.client = Client()
        self.signup_url = reverse("signup")
        
        # Create a minimal SocialApp for template rendering
        site = Site.objects.get_or_create(id=1, defaults={"name": "Test Site", "domain": "testserver"})[0]
        social_app, created = SocialApp.objects.get_or_create(
            provider='google',
            defaults={
                'name': 'Google (test)',
                'client_id': 'test-client-id'
            }
        )
        social_app.sites.add(site)
        
        # Create an existing user for duplicate email test
        self.existing_user = User.objects.create_user(
            email="existing@example.com",
            password="existingpass123",
            first_name="Existing",
            last_name="User",
            is_active=True
        )

    def test_signup_shows_error_for_duplicate_email(self):
        """
        Test that signup shows error when email already exists in database
        """
        print("\nTEST: Signup with duplicate email (existing@example.com)")
        print("EXPECTED: Signup fails with error about duplicate email, user count stays at 1")
        
        post_data = {
            "first-name": "New",
            "last-name": "User",
            "email": "existing@example.com",
            "password1": "newpass123",
            "password2": "newpass123",
            "phone-number": "1234567890"
        }

        response = self.client.post(self.signup_url, post_data, follow=True)
        messages_list = list(get_messages(response.wsgi_request))
        actual_message = str(messages_list[0]) if messages_list else "No message"
        user_count = User.objects.filter(email="existing@example.com").count()
        print(f"ACTUAL: message='{actual_message}', user_count={user_count}")
        
        # Check that error message is displayed
        self.assertEqual(len(messages_list), 1)
        print("Assertion 1 PASS: exactly 1 error message displayed")
        self.assertEqual(
            actual_message,
            "An account with that email already exists."
        )
        print("Assertion 2 PASS: error message matches expected")
        
        # Verify user count hasn't increased
        self.assertEqual(User.objects.filter(email="existing@example.com").count(), 1)
        print("Assertion 3 PASS: no new user was created")

    def test_signup_shows_error_for_invalid_email_format(self):
        """
        Test that signup shows error when email format is invalid
        """
        print("\nTEST: Signup with invalid email format (notanemail - missing domain)")
        print("EXPECTED: Signup fails with error about invalid email format, no user created")
        
        post_data = {
            "first-name": "New",
            "last-name": "User",
            "email": "notanemail",  # Invalid email format (missing @domain)
            "password1": "newpass123",
            "password2": "newpass123",
            "phone-number": "1234567890"
        }

        response = self.client.post(self.signup_url, post_data, follow=True)
        messages_list = list(get_messages(response.wsgi_request))
        actual_message = str(messages_list[0]) if messages_list else "No message"
        user_count = User.objects.filter(email="notanemail").count()
        print(f"ACTUAL: message='{actual_message}', user_count={user_count}")
        
        # Check that error message about invalid email is displayed
        self.assertEqual(len(messages_list), 1)
        print("Assertion 1 PASS: exactly 1 error message displayed")
        self.assertEqual(
            actual_message,
            "Please enter a valid email address."
        )
        print("Assertion 2 PASS: error message matches expected")
        
        # Verify no user was created with invalid email
        self.assertEqual(User.objects.filter(email="notanemail").count(), 0)
        print("Assertion 3 PASS: no user was created with invalid email")

    def test_signup_success_with_valid_data(self):
        """
        Test that signup succeeds with valid email and password
        """
        print("\nTEST: Signup with valid data (john@example.com, password=securepass123)")
        print("EXPECTED: User successfully created with first_name=John, last_name=Doe, email=john@example.com")
        
        post_data = {
            "first-name": "John",
            "last-name": "Doe",
            "email": "john@example.com",
            "password1": "securepass123",
            "password2": "securepass123",
            "phone-number": "5551234567"
        }

        response = self.client.post(self.signup_url, post_data, follow=True)

        # Verify user details
        new_user = User.objects.get(email="john@example.com")
        print(f"ACTUAL: User created with first_name={new_user.first_name}, last_name={new_user.last_name}, email={new_user.email}")
        
        # Verify user was created
        self.assertTrue(User.objects.filter(email="john@example.com").exists())
        print("Assertion 1 PASS: user was created with email john@example.com")

        self.assertEqual(new_user.first_name, "John")
        print("Assertion 2 PASS: first_name == 'John'")
        self.assertEqual(new_user.last_name, "Doe")
        print("Assertion 3 PASS: last_name == 'Doe'")
        self.assertEqual(new_user.email, "john@example.com")
        print("Assertion 4 PASS: email == 'john@example.com'")




# Create your tests here.

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

# *** 404 Page Not Found Tests ***
class PageNotFoundTests(TestCase):
    # Test that non existant page returns 404
    def test_404_page_returns_404(self):
        resp = self.client.get("/fake-page-test/")
        self.assertEqual(resp.status_code, 404)

    # Tests if the custom 404 template is rendered instead of Django default
    def test_404_uses_custom_template(self):
        resp = self.client.get("/fake-page-test/")
        self.assertTemplateUsed(resp, "404.html")
