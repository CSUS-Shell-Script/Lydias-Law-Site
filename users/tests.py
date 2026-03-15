import re

from django.contrib.messages import get_messages
from django.core import mail
from django.test import TestCase, Client, override_settings
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
        self.assertIn("Invalid password.", self._messages(resp))


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
            "Invalid password."
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
            "Invalid password."
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

    def test_signup_password_mismatch_preserves_non_password_fields(self):
        """
        On password mismatch, non-password fields should be preserved while
        password fields remain blank.
        """
        post_data = {
            "first-name": "Jane",
            "last-name": "Smith",
            "email": "jane@example.com",
            "password1": "Password1!",
            "password2": "DifferentPassword1!",
            "phone-number": "1234567890",
        }

        response = self.client.post(self.signup_url, post_data, follow=True)
        messages_list = list(get_messages(response.wsgi_request))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Passwords do not match.", [str(m) for m in messages_list])

        form_data = response.context.get("form_data", {})
        self.assertEqual(form_data.get("first_name"), "Jane")
        self.assertEqual(form_data.get("last_name"), "Smith")
        self.assertEqual(form_data.get("email"), "jane@example.com")
        self.assertEqual(form_data.get("phone_number"), "1234567890")

        content = response.content.decode()
        self.assertNotIn('name="password1" value="Password1!"', content)
        self.assertNotIn('name="password2" value="DifferentPassword1!"', content)

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


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordResetFlowTests(TestCase):
    def setUp(self):
        self.client = Client()
        site = Site.objects.get_or_create(
            id=1,
            defaults={"name": "Test Site", "domain": "testserver"},
        )[0]
        social_app, _ = SocialApp.objects.get_or_create(
            provider="google",
            defaults={"name": "Google (test)", "client_id": "test-client-id"},
        )
        social_app.sites.add(site)

        self.reset_url = reverse("account_reset_password")
        self.client_user = User.objects.create_user(
            email="client@example.com",
            password="Password123!",
            first_name="Client",
            last_name="User",
            role=User.Role.CLIENT,
            is_active=True,
        )
        EmailAddress.objects.create(
            user=self.client_user,
            email=self.client_user.email,
            verified=True,
            primary=True,
        )

        self.admin_user = User.objects.create_user(
            email="admin@example.com",
            password="AdminPass123!",
            first_name="Admin",
            last_name="User",
            role=User.Role.ADMIN,
            is_staff=True,
            is_active=True,
        )
        EmailAddress.objects.create(
            user=self.admin_user,
            email=self.admin_user.email,
            verified=True,
            primary=True,
        )

    def _extract_reset_path(self, email_body):
        match = re.search(r"https?://testserver(?P<path>/accounts/password/reset/key/[^\s]+)", email_body)
        self.assertIsNotNone(match)
        return match.group("path")

    def test_reset_route_is_canonical_accounts_path(self):
        self.assertEqual(self.reset_url, "/accounts/password/reset/")

    def test_login_page_links_to_password_reset(self):
        response = self.client.get(reverse("login"))
        self.assertContains(response, 'href="/accounts/password/reset/"', html=False)

    def test_reset_request_uses_generic_success_for_unknown_email(self):
        response = self.client.post(
            self.reset_url,
            {"email": "missing@example.com"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "account/password_reset_done.html")
        self.assertContains(
            response,
            "If an active account matches that email address, we have sent password reset instructions.",
        )
        self.assertNotContains(response, "missing@example.com")

    def test_reset_request_sends_branded_email_for_existing_account(self):
        response = self.client.post(
            self.reset_url,
            {"email": self.client_user.email},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "account/password_reset_done.html")
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(mail.outbox[0].subject.endswith("Reset your Lydia's Law password"))
        self.assertIn("Reset password", mail.outbox[0].alternatives[0][0])
        self.assertIn("/accounts/password/reset/key/", mail.outbox[0].body)

    def test_reset_form_renders_invalid_link_state(self):
        url = reverse(
            "account_reset_password_from_key",
            kwargs={"uidb36": "abc123", "key": "invalid"},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "account/password_reset_from_key.html")
        self.assertContains(response, "Reset link expired or invalid")
        self.assertContains(response, reverse("account_reset_password"))

    def test_reset_form_shows_server_side_password_validation_errors(self):
        self.client.post(self.reset_url, {"email": self.client_user.email}, follow=True)
        reset_path = self._extract_reset_path(mail.outbox[0].body)
        get_response = self.client.get(reset_path, follow=True)

        post_response = self.client.post(
            get_response.request["PATH_INFO"],
            {
                "password1": "short1",
                "password2": "short1",
            },
        )

        self.assertEqual(post_response.status_code, 200)
        self.assertTemplateUsed(post_response, "account/password_reset_from_key.html")
        self.assertContains(post_response, "This password is too short")

    def test_successful_password_reset_sends_notification_email(self):
        self.client.post(self.reset_url, {"email": self.client_user.email}, follow=True)
        reset_path = self._extract_reset_path(mail.outbox[0].body)

        get_response = self.client.get(reset_path, follow=True)
        self.assertEqual(get_response.status_code, 200)
        self.assertTemplateUsed(get_response, "account/password_reset_from_key.html")

        post_response = self.client.post(
            get_response.request["PATH_INFO"],
            {
                "password1": "NewSecurePass123!",
                "password2": "NewSecurePass123!",
            },
            follow=True,
        )

        self.client_user.refresh_from_db()
        self.assertTrue(self.client_user.check_password("NewSecurePass123!"))
        self.assertEqual(post_response.status_code, 200)
        self.assertTemplateUsed(post_response, "account/password_reset_from_key_done.html")
        self.assertEqual(len(mail.outbox), 2)
        self.assertTrue(mail.outbox[1].subject.endswith("Your Lydia's Law password was changed"))
        self.assertIn("password for your Lydia's Law account was changed", mail.outbox[1].body)

    def test_client_password_change_redirects_back_to_account(self):
        self.client.force_login(self.client_user)

        response = self.client.post(
            reverse("account_change_password"),
            {
                "oldpassword": "Password123!",
                "password1": "UpdatedPass123!",
                "password2": "UpdatedPass123!",
            },
        )

        self.client_user.refresh_from_db()
        self.assertRedirects(response, reverse("client_account"), fetch_redirect_response=False)
        self.assertTrue(self.client_user.check_password("UpdatedPass123!"))

    def test_admin_password_change_redirects_to_admin_dashboard(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse("account_change_password"),
            {
                "oldpassword": "AdminPass123!",
                "password1": "AdminUpdated123!",
                "password2": "AdminUpdated123!",
            },
        )

        self.admin_user.refresh_from_db()
        self.assertRedirects(response, reverse("admin_dashboard"), fetch_redirect_response=False)
        self.assertTrue(self.admin_user.check_password("AdminUpdated123!"))

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
from django.test import TestCase, override_settings, Client

class InternalServerErrorTests(TestCase):

    @override_settings(DEBUG=False)
    def test_500_page_returns_500(self):
        client = Client(raise_request_exception=False)
        resp = client.get("/test-500/")
        self.assertEqual(resp.status_code, 500)

    @override_settings(DEBUG=False)
    def test_500_uses_custom_template(self):
        client = Client(raise_request_exception=False)
        resp = client.get("/test-500/")
        self.assertTemplateUsed(resp, "500.html")