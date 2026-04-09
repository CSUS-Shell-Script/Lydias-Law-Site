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
        print("EXPECTED: Login fails since user is inactive, status=403, user not authenticated")
        
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
        self.assertEqual(len(messages_list), 1)
        print("Assertion 2 PASS: exactly 1 error message displayed")
        self.assertEqual(
            actual_message,
            "Please verify your email to activate your account."
        )
        print("Assertion 3 PASS: error message matches expected")
        
        # Check response status code indicates an error (403 for inactive)
        self.assertEqual(response.status_code, 403)
        print("Assertion 4 PASS: response.status_code == 403")

    def test_staff_login_page_shows_distinct_copy_and_client_login_link(self):
        response = self.client.get(self.login_url, {"role": "admin"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Staff login")
        self.assertContains(response, "Authorized staff only")
        self.assertContains(response, "Client login")
        self.assertContains(response, f'href="{self.login_url}"')

    def test_client_login_page_links_to_staff_login(self):
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Are you an Admin?")
        self.assertContains(response, f'href="{self.login_url}?role=admin"')

    def test_staff_login_page_shows_distinct_copy_and_client_login_link(self):
        response = self.client.get(self.login_url, {"role": "admin"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Staff login")
        self.assertContains(response, "Authorized staff only")
        self.assertContains(response, "Client login")
        self.assertContains(response, f'href="{self.login_url}"')

    def test_client_login_page_links_to_staff_login(self):
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Are you an Admin?")
        self.assertContains(response, f'href="{self.login_url}?role=admin"')


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
        print("\nTEST: Signup with password mismatch preserves non-password fields")
        print("EXPECTED: Passwords do not match message, non-password fields preserved, password fields blank")
        
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
        form_data = response.context.get("form_data", {})
        content = response.content.decode()
        print(f"ACTUAL: status_code={response.status_code}, messages={[str(m) for m in messages_list]}, form_data={form_data}")
        
        self.assertEqual(response.status_code, 200)
        print("Assertion 1 PASS: status_code == 200")
        self.assertIn("Passwords do not match.", [str(m) for m in messages_list])
        print("Assertion 2 PASS: 'Passwords do not match.' message displayed")

        self.assertEqual(form_data.get("first_name"), "Jane")
        print("Assertion 3 PASS: first_name preserved")
        self.assertEqual(form_data.get("last_name"), "Smith")
        print("Assertion 4 PASS: last_name preserved")
        self.assertEqual(form_data.get("email"), "jane@example.com")
        print("Assertion 5 PASS: email preserved")
        self.assertEqual(form_data.get("phone_number"), "1234567890")
        print("Assertion 6 PASS: phone_number preserved")

        self.assertNotIn('name="password1" value="Password1!"', content)
        print("Assertion 7 PASS: password1 field blank")
        self.assertNotIn('name="password2" value="DifferentPassword1!"', content)
        print("Assertion 8 PASS: password2 field blank")

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

    def test_signup_blank_first_name_rejected(self):
        """
        Test that signup rejects blank first name
        """
        print("\nTEST: Signup with blank first name")
        print("EXPECTED: Signup rejected with 'All fields must be filled in' message, no user created")
        
        post_data = {
            "first-name": "",
            "last-name": "Doe",
            "email": "john@example.com",
            "password1": "securepass123",
            "password2": "securepass123",
            "phone-number": "5551234567"
        }
        response = self.client.post(self.signup_url, post_data, follow=True)
        messages_list = list(get_messages(response.wsgi_request))
        user_exists = User.objects.filter(email="john@example.com").exists()
        print(f"ACTUAL: messages={[str(m) for m in messages_list]}, user_exists={user_exists}")
        
        self.assertIn("All fields must be filled in", [str(m) for m in messages_list])
        print("Assertion 1 PASS: 'All fields must be filled in' message displayed")
        self.assertFalse(user_exists)
        print("Assertion 2 PASS: no user created")

    def test_signup_blank_last_name_rejected(self):
        """
        Test that signup rejects blank last name
        """
        print("\nTEST: Signup with blank last name")
        print("EXPECTED: Signup rejected with 'All fields must be filled in' message, no user created")
        
        post_data = {
            "first-name": "John",
            "last-name": "",
            "email": "john@example.com",
            "password1": "securepass123",
            "password2": "securepass123",
            "phone-number": "5551234567"
        }
        response = self.client.post(self.signup_url, post_data, follow=True)
        messages_list = list(get_messages(response.wsgi_request))
        user_exists = User.objects.filter(email="john@example.com").exists()
        print(f"ACTUAL: messages={[str(m) for m in messages_list]}, user_exists={user_exists}")
        
        self.assertIn("All fields must be filled in", [str(m) for m in messages_list])
        print("Assertion 1 PASS: 'All fields must be filled in' message displayed")
        self.assertFalse(user_exists)
        print("Assertion 2 PASS: no user created")

    def test_signup_blank_phone_number_rejected(self):
        """
        Test that signup rejects blank phone number
        """
        print("\nTEST: Signup with blank phone number")
        print("EXPECTED: Signup rejected with 'All fields must be filled in' message, no user created")
        
        post_data = {
            "first-name": "John",
            "last-name": "Doe",
            "email": "john@example.com",
            "password1": "securepass123",
            "password2": "securepass123",
            "phone-number": ""
        }
        response = self.client.post(self.signup_url, post_data, follow=True)
        messages_list = list(get_messages(response.wsgi_request))
        user_exists = User.objects.filter(email="john@example.com").exists()
        print(f"ACTUAL: messages={[str(m) for m in messages_list]}, user_exists={user_exists}")
        
        self.assertIn("All fields must be filled in", [str(m) for m in messages_list])
        print("Assertion 1 PASS: 'All fields must be filled in' message displayed")
        self.assertFalse(user_exists)
        print("Assertion 2 PASS: no user created")

    def test_signup_phone_number_format_validation(self):
        """
        Test that signup validates phone number format
        """
        print("\nTEST: Signup with invalid phone number format")
        print("EXPECTED: Signup rejected with 'Please enter a valid phone number.' message, no user created")
        
        post_data = {
            "first-name": "John",
            "last-name": "Doe",
            "email": "john@example.com",
            "password1": "securepass123",
            "password2": "securepass123",
            "phone-number": "abc123"  # Invalid format
        }
        response = self.client.post(self.signup_url, post_data, follow=True)
        messages_list = list(get_messages(response.wsgi_request))
        user_exists = User.objects.filter(email="john@example.com").exists()
        print(f"ACTUAL: messages={[str(m) for m in messages_list]}, user_exists={user_exists}")
        
        self.assertIn("Please enter a valid phone number.", [str(m) for m in messages_list])
        print("Assertion 1 PASS: 'Please enter a valid phone number.' message displayed")
        self.assertFalse(user_exists)
        print("Assertion 2 PASS: no user created")

    def test_signup_successful_registration_creates_guest_user_inactive(self):
        """
        Test that successful registration creates user with GUEST role and is_active=False
        """
        print("\nTEST: Successful signup creates guest user inactive")
        print("EXPECTED: User created with role=GUEST and is_active=False")
        
        post_data = {
            "first-name": "Jane",
            "last-name": "Smith",
            "email": "jane@example.com",
            "password1": "securepass123",
            "password2": "securepass123",
            "phone-number": "555-123-4567"
        }
        response = self.client.post(self.signup_url, post_data, follow=True)
        new_user = User.objects.get(email="jane@example.com")
        print(f"ACTUAL: role={new_user.role}, is_active={new_user.is_active}")
        
        self.assertEqual(new_user.role, User.Role.GUEST)
        print("Assertion 1 PASS: role == GUEST")
        self.assertFalse(new_user.is_active)
        print("Assertion 2 PASS: is_active == False")

    def test_signup_creates_email_verification_record(self):
        """
        Test that signup creates EmailAddress with verified=False
        """
        print("\nTEST: Signup creates email verification record")
        print("EXPECTED: EmailAddress created with verified=False and primary=True")
        
        post_data = {
            "first-name": "Jane",
            "last-name": "Smith",
            "email": "jane@example.com",
            "password1": "securepass123",
            "password2": "securepass123",
            "phone-number": "555-123-4567"
        }
        response = self.client.post(self.signup_url, post_data, follow=True)
        email_address = EmailAddress.objects.get(email="jane@example.com")
        print(f"ACTUAL: verified={email_address.verified}, primary={email_address.primary}")
        
        self.assertFalse(email_address.verified)
        print("Assertion 1 PASS: verified == False")
        self.assertTrue(email_address.primary)
        print("Assertion 2 PASS: primary == True")


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
        print("\nTEST: Guest user accessing admin dashboard")
        print("EXPECTED: Returns 403 Forbidden")
        
        resp = self.client.get(self.url)
        print(f"ACTUAL: status_code={resp.status_code}")
        
        self.assertEqual(resp.status_code, 403)
        print("Assertion 1 PASS: status_code == 403")

    # Test for client user -> logged in
    # Should get 403 page
    def test_client_user_gets_403(self):
        print("\nTEST: Client user accessing admin dashboard")
        print("EXPECTED: Returns 403 Forbidden")
        
        self.client.login(email="client@unitTest.com", password="Password1!")
        resp = self.client.get(self.url)
        print(f"ACTUAL: status_code={resp.status_code}")
        
        self.assertEqual(resp.status_code, 403)
        print("Assertion 1 PASS: status_code == 403")

    # Test for admin user -> logged in
    # Should NOT get 403 page
    def test_superuser_gets_200(self):
        print("\nTEST: Superuser accessing admin dashboard")
        print("EXPECTED: Returns 200 OK and uses admin/dashboard.html template")
        
        self.client.login(email="admin@unitTest.com", password="Pass12345!")
        resp = self.client.get(self.url)
        template_used = resp.templates[0].name if resp.templates else "No template"
        print(f"ACTUAL: status_code={resp.status_code}, template='{template_used}'")
        
        self.assertEqual(resp.status_code, 200)
        print("Assertion 1 PASS: status_code == 200")
        self.assertTemplateUsed(resp, "admin/dashboard.html")
        print("Assertion 2 PASS: template used is admin/dashboard.html")
        
    # Tests if custom 403 template is rendered instead of Django default
    def test_403_uses_custom_template(self):
        print("\nTEST: Client user accessing admin dashboard gets 403 with custom template")
        print("EXPECTED: Returns 403 Forbidden and uses 403.html template")
        
        self.client.login(email="client@unitTest.com", password="Password1!")
        resp = self.client.get(self.url)
        template_used = resp.templates[0].name if resp.templates else "No template"
        print(f"ACTUAL: status_code={resp.status_code}, template='{template_used}'")
        
        self.assertEqual(resp.status_code, 403)
        print("Assertion 1 PASS: status_code == 403")
        self.assertTemplateUsed(resp, "403.html")
        print("Assertion 2 PASS: template used is 403.html")
        
# *** 404 Page Not Found Tests ***
class PageNotFoundTests(TestCase):
    # Test that non existant page returns 404
    def test_404_page_returns_404(self):
        print("\nTEST: Accessing non-existent page")
        print("EXPECTED: Returns 404 Not Found")
        
        resp = self.client.get("/fake-page-test/")
        print(f"ACTUAL: status_code={resp.status_code}")
        
        self.assertEqual(resp.status_code, 404)
        print("Assertion 1 PASS: status_code == 404")

    # Tests if the custom 404 template is rendered instead of Django default
    def test_404_uses_custom_template(self):
        print("\nTEST: Accessing non-existent page uses custom 404 template")
        print("EXPECTED: Uses 404.html template")
        
        resp = self.client.get("/fake-page-test/")
        template_used = resp.templates[0].name if resp.templates else "No template"
        print(f"ACTUAL: template='{template_used}'")
        
        self.assertTemplateUsed(resp, "404.html")
        print("Assertion 1 PASS: template used is 404.html")

class InternalServerErrorTests(TestCase):

    @override_settings(DEBUG=False)
    def test_500_page_returns_500(self):
        print("\nTEST: Accessing test 500 page")
        print("EXPECTED: Returns 500 Internal Server Error")
        
        client = Client(raise_request_exception=False)
        resp = client.get("/test-500/")
        print(f"ACTUAL: status_code={resp.status_code}")
        
        self.assertEqual(resp.status_code, 500)
        print("Assertion 1 PASS: status_code == 500")

    @override_settings(DEBUG=False)
    def test_500_uses_custom_template(self):
        print("\nTEST: Accessing test 500 page uses custom 500 template")
        print("EXPECTED: Uses 500.html template")
        
        client = Client(raise_request_exception=False)
        resp = client.get("/test-500/")
        template_used = resp.templates[0].name if resp.templates else "No template"
        print(f"ACTUAL: template='{template_used}'")
        
        self.assertTemplateUsed(resp, "500.html")
        print("Assertion 1 PASS: template used is 500.html")


# LLW-299 Form security and validation 
class FormSecurityTests(TestCase):

    # Set up Admin and Client user data
    def setUp(self):
        self.admin_user = User.objects.create_user(
            email="admin@example.com",
            password="pw",
            first_name="Admin",
            last_name="User",
            is_staff=True,
            is_active=True,
        )

        self.client_password = "OldUniqueSecret456!"
        self.client_user = User.objects.create_user(
            email="client@example.com",
            password=self.client_password,
            first_name="Client",
            last_name="User",
            is_staff=False,
            is_active=True,
        )

        site = Site.objects.get_or_create(
            id=1,
            defaults={"name": "Test Site", "domain": "testserver"}
        )[0]

        social_app, created = SocialApp.objects.get_or_create(
            provider="google",
            defaults={
                "name": "Google (test)",
                "client_id": "test-client-id",
            }
        )
        social_app.sites.add(site)

    def _extract_csrf_token(self, response):
        content = response.content.decode("utf-8")
        match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', content)
        self.assertIsNotNone(match, "Could not find csrfmiddlewaretoken in response HTML")
        return match.group(1)

    # EMAIL VALIDATION TESTS
    # Signup email validation already done under SignupTests class (function: test_signup_shows_error_for_invalid_email_format)
    # Test: Login rejects invalid email
    def test_login_rejects_invalid_email(self):
        response = self.client.post(reverse("login"), {
            "email": "not-an-email",
            "password": "whatever123",
        }, follow=True)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    # Test: Reject if email doesn't belong to an existing user (invoice creation only checks for existing user email)
    def test_invoice_creation_rejects_invalid_email(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(reverse("admin_create_invoices"), {
            "client_name": "Client One",
            "client_email": "bad-email",
            "amount": "250.00",
            "description": "Invoice test",
        })
        self.assertEqual(response.status_code, 200)


    # CSRF TOKEN PRESENCE TESTS
    # Test: Login form has csrf token
    def test_login_form_contains_csrf_token(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_login_get_is_never_cached(self):
        response = self.client.get(reverse("login"))
        cache_control = response.headers.get("Cache-Control", "")
        self.assertIn("no-store", cache_control)
        self.assertIn("no-cache", cache_control)
        pragma = response.headers.get("Pragma")
        if pragma is not None:
            self.assertEqual(pragma, "no-cache")

    def test_authenticated_client_get_login_redirects_to_client_dashboard(self):
        self.client.force_login(self.client_user)
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("client_dashboard"))

    def test_authenticated_staff_get_login_redirects_to_admin_dashboard(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("admin_dashboard"))

    def test_login_reusing_stale_csrf_token_returns_403(self):
        """
        Simulate the real-world back-button cached-form scenario:
        - user loads login page (token A)
        - user logs in (Django rotates CSRF token/cookie)
        - user submits cached login form again (still token A) -> 403
        """
        csrf_client = Client(enforce_csrf_checks=True)

        first_get = csrf_client.get(reverse("login"))
        token_a = self._extract_csrf_token(first_get)

        login_resp = csrf_client.post(
            reverse("login"),
            {
                "email": "client@example.com",
                "password": self.client_password,
                "csrfmiddlewaretoken": token_a,
            },
            follow=False,
        )
        self.assertIn(login_resp.status_code, [302, 303])

        stale_post = csrf_client.post(
            reverse("login"),
            {
                "email": "client@example.com",
                "password": self.client_password,
                "csrfmiddlewaretoken": token_a,
            },
            follow=False,
        )
        self.assertEqual(stale_post.status_code, 403)
        self.assertIn("CSRF", stale_post.content.decode("utf-8"))

    def test_inactive_user_login_returns_403_with_verify_message(self):
        inactive_email = "inactive@example.com"
        inactive_password = "SomePassword_123!"
        User.objects.create_user(
            email=inactive_email,
            password=inactive_password,
            first_name="Inactive",
            last_name="User",
            is_staff=False,
            is_active=False,
        )

        response = self.client.post(
            reverse("login"),
            {"email": inactive_email, "password": inactive_password},
            follow=True,
        )
        self.assertEqual(response.status_code, 403)
        messages_list = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("Please verify your email to activate your account.", messages_list)

    # Test: Signup form has csrf token
    def test_signup_form_contains_csrf_token(self):
        response = self.client.get(reverse("signuppage"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "csrfmiddlewaretoken")

    # Test: Client account modal forms have csrf token
    def test_account_settings_modal_contains_csrf_token(self):
        self.client.force_login(self.client_user)
        response = self.client.get(reverse("client_account"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="editForm"')
        self.assertContains(response, "csrfmiddlewaretoken")

    # Test: Client account modal forms fails without csrf token
    def test_account_settings_modal_post_without_csrf_fails(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.client_user)
        response = csrf_client.post(reverse("client_account"), {
            "field": "phone",
            "new_value": "1234567890",
        })
        self.assertEqual(response.status_code, 403)

    # Test: Admin invoice creation page has csrf token
    def test_invoice_creation_form_contains_csrf_token(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("admin_create_invoices"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "csrfmiddlewaretoken")

    # Test: Guest User invoice payment page has csrf token
    def test_invoice_payment_form_contains_csrf_token(self):
        response = self.client.get(reverse("payment"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "csrfmiddlewaretoken")

    # Test: Forgot password page has csrf token
    def test_forgot_password_form_contains_csrf_token(self):
        response = self.client.get(reverse("account_reset_password"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "csrfmiddlewaretoken")

    # Test: Change password page has csrf token
    def test_change_password_form_contains_csrf_token(self):
        self.client.force_login(self.client_user)
        response = self.client.get(reverse("account_change_password"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "csrfmiddlewaretoken")


    # PASSWORD NOT RETURNED IN RESPONSE TESTS
    # Test: Password field not returned in any response context or HTML output
    def _assert_passwords_not_exposed(self, response, *passwords):
        content = response.content.decode()

        for password in passwords:
            self.assertNotIn(
                f'value="{password}"',
                content,
                f"Password value was rendered into an HTML input: {password!r}"
            )
            self.assertNotIn(
                password,
                content,
                f"Password was found in response body: {password!r}"
            )

        if response.context:
            for ctx in response.context:
                flat_ctx = ctx.flatten()
                for value in flat_ctx.values():
                    if isinstance(value, str):
                        for password in passwords:
                            self.assertNotIn(
                                password,
                                value,
                                f"Password was found in response context string: {password!r}"
                            )

    # Test: Login page doesn't render password if login failed (wrong password)
    def test_login_password_not_rendered_in_response(self):
        password = "WrongSecretPass_987!"
        response = self.client.post(
            reverse("login"),
            {
                "email": "client@example.com",
                "password": password,
            },
            follow=True,
        )
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self._assert_passwords_not_exposed(response, password)

    # Test: Login page doesn't render password if login successful (correct password)
    def test_login_with_valid_password_authenticates_user(self):
        response = self.client.post(
            reverse("login"),
            {
                "email": "client@example.com",
                "password": self.client_password,
            },
            follow=True,
        )
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self._assert_passwords_not_exposed(response, self.client_password)

    # Test: Signup password page doesn't render password
    def test_signup_password_not_rendered_in_response(self):
        password = "NewSuperSecretPass123!"
        response = self.client.post(
            reverse("signuppage"),
            {
                "first-name": "Client",
                "last-name": "User",
                "email": "client@example.com",
                "phone-number": "1234567890",
                "password1": password,
                "password2": password,
            },
            follow=True,
        )
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self._assert_passwords_not_exposed(response, password)

    # Test: Forgot password page doesn't render password
    def test_forgot_password_response_does_not_render_passwords(self):
        injected_password = "ForgotSecretPass555!"
        response = self.client.post(
            reverse("account_reset_password"),
            {
                "email": "client@example.com",
                "password1": injected_password,
                "password2": injected_password,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self._assert_passwords_not_exposed(response, injected_password)

    # Test: Change password page doesn't render password
    def test_change_password_response_does_not_render_passwords(self):
        self.client.force_login(self.client_user)
        old_password = self.client_password
        new_password = "NewSuperSecretPass123!"

        response = self.client.post(
            reverse("account_change_password"),
            {
                "oldpassword": old_password,
                "password1": new_password,
                "password2": new_password,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self._assert_passwords_not_exposed(response, old_password, new_password)

# USER MODEL TEST - LLW-302 ****
class UserModelTest(TestCase):
    # --- Custom user creation via email ---
    def test_create_user_with_email(self):
        """User is created with email as the unique identifier."""
        user = User.objects.create_user(
            email="test@test.com",
            password="Pass123!",
        )
        self.assertEqual(user.email, "test@test.com")
    def test_username_field_is_none(self):
        """Username field should be None — email is used instead."""
        user = User.objects.create_user(
            email="test@test.com",
            password="Pass123!",
        )
        self.assertIsNone(user.username)

    def test_create_user_without_email_raises_error(self):
        """Creating a user without an email should raise a ValueError."""
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password="Pass123!")

    def test_user_email_is_unique(self):
        """Two users cannot share the same email."""
        User.objects.create_user(email="unique@test.com", password="Pass123!")
        with self.assertRaises(Exception):
            User.objects.create_user(email="unique@test.com", password="Pass123!")

    def test_password_is_hashed(self):
        """Password should be stored hashed, not in plain text."""
        user = User.objects.create_user(
            email="test@test.com",
            password="Pass123!",
        )
        self.assertNotEqual(user.password, "Pass123!")
        self.assertTrue(user.check_password("Pass123!"))

    # --- Superuser creation ---
    def test_create_superuser_sets_is_staff(self):
        """create_superuser should set is_staff=True."""
        user = User.objects.create_superuser(
            email="super@test.com",
            password="Pass123!",
        )
        self.assertTrue(user.is_staff)

    def test_create_superuser_sets_is_superuser(self):
        """create_superuser should set is_superuser=True."""
        user = User.objects.create_superuser(
            email="super@test.com",
            password="Pass123!",
        )
        self.assertTrue(user.is_superuser)

    def test_create_superuser_without_is_staff_raises_error(self):
        """create_superuser should raise ValueError if is_staff=False."""
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email="super@test.com",
                password="Pass123!",
                is_staff=False,
            )

    def test_create_superuser_without_is_superuser_raises_error(self):
        """create_superuser should raise ValueError if is_superuser=False."""
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email="super@test.com",
                password="Pass123!",
                is_superuser=False,
            )

    # --- Role choices ---
    def test_default_role_is_guest(self):
        """New users should default to GUEST role."""
        user = User.objects.create_user(
            email="test@test.com",
            password="Pass123!",
        )
        self.assertEqual(user.role, User.Role.GUEST)

    def test_role_can_be_set_to_client(self):
        """User role can be set to CLIENT."""
        user = User.objects.create_user(
            email="test@test.com",
            password="Pass123!",
            role=User.Role.CLIENT,
        )
        self.assertEqual(user.role, User.Role.CLIENT)

    def test_role_can_be_set_to_admin(self):
        """User role can be set to ADMIN."""
        user = User.objects.create_user(
            email="test@test.com",
            password="Pass123!",
            role=User.Role.ADMIN,
        )
        self.assertEqual(user.role, User.Role.ADMIN)

    # --- retainer_balance defaults to 0 ---
    def test_retainer_balance_defaults_to_zero(self):
        """retainer_balance should default to 0."""
        user = User.objects.create_user(
            email="test@test.com",
            password="Pass123!",
        )
        self.assertEqual(user.retainer_balance, 0)

    # --- Phone number stored correctly ---
    def test_phone_number_stores_correctly(self):
        """Phone number should be saved and retrieved correctly."""
        user = User.objects.create_user(
            email="test@test.com",
            password="Pass123!",
            phone_number="9165551234",
        )
        self.assertEqual(user.phone_number, "9165551234")

    def test_phone_number_defaults_to_none(self):
        """Phone number should be None if not provided."""
        user = User.objects.create_user(
            email="test@test.com",
            password="Pass123!",
        )
        self.assertIsNone(user.phone_number)

    # --- payment_provider and provider_customer_id ---
    def test_payment_provider_defaults_to_none(self):
        """payment_provider should be None if not set."""
        user = User.objects.create_user(
            email="test@test.com",
            password="Pass123!",
        )
        self.assertIsNone(user.payment_provider)

    def test_provider_customer_id_defaults_to_none(self):
        """provider_customer_id should be None if not set."""
        user = User.objects.create_user(
            email="test@test.com",
            password="Pass123!",
        )
        self.assertIsNone(user.provider_customer_id)

    def test_payment_provider_stores_correctly(self):
        """payment_provider should be saved and retrieved correctly."""
        user = User.objects.create_user(
            email="test@test.com",
            password="Pass123!",
            payment_provider="stripe",
            provider_customer_id="cus_abc123",
        )
        self.assertEqual(user.payment_provider, "stripe")
        self.assertEqual(user.provider_customer_id, "cus_abc123")

