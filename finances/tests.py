from django.contrib.messages import get_messages
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, MagicMock

from allauth.socialaccount.models import SocialApp

from finances.models import Invoice
from users.models import AdminProfile

import json

User = get_user_model()



class GuestInvoiceIdValidationTests(TestCase):
    def _messages(self, response):
        return [m.message for m in get_messages(response.wsgi_request)]

    def test_payment_post_with_invalid_invoice_id_shows_error(self):
        url = reverse("payment")
        resp = self.client.post(url, data={"invoice_id": "999999"}, follow=True)
        self.assertEqual(resp.status_code, 404)
        self.assertIn("Incorrect Invoice ID.", self._messages(resp))

    def test_payment_post_with_valid_invoice_id_redirects_to_checkout(self):
        user = User.objects.create_user(
            email="client@example.com",
            password="pw",
            first_name="Client",
            last_name="User",
            is_staff=False,
            is_active=True,
        )
        inv = Invoice.objects.create(
            user=user,
            amount=12345,
            status=Invoice.Status.PENDING,
        )

        url = reverse("payment")
        resp = self.client.post(url, data={"invoice_id": str(inv.id)})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("create_checkout_session", args=[inv.id]))

class InvoiceCreationTests(TestCase):
    """Test invoice creation functionality and error messages"""

    def setUp(self):
        """Set up test client, admin user, and test users"""
        self.client = Client()
        self.create_invoice_url = reverse("admin_create_invoices")
        
        # Create a minimal SocialApp to prevent allauth template tag errors
        site = Site.objects.get_or_create(id=1, defaults={"name": "Test Site", "domain": "testserver"})[0]
        social_app, created = SocialApp.objects.get_or_create(
            provider='google',
            defaults={
                'name': 'Google (test)',
                'client_id': 'test-client-id'
            }
        )
        social_app.sites.add(site)
        
        # Create an admin user
        self.admin_user = User.objects.create_user(
            email="admin@example.com",
            password="adminpass123",
            first_name="Admin",
            last_name="User",
            is_active=True,
            is_staff=True
        )
        
        # Create admin profile for the admin user
        AdminProfile.objects.create(user=self.admin_user, hourly_rate=150.00)
        
        # Create a test client user for invoice creation
        self.client_user = User.objects.create_user(
            email="client@example.com",
            password="clientpass123",
            first_name="Test",
            last_name="Client",
            is_active=True
        )
        
        # Log in the admin user for all requests
        self.client.login(email="admin@example.com", password="adminpass123")

    def test_create_invoice_with_invalid_email_format(self):
        """
        Test that invoice creation fails when email format is invalid
        """
        print("\nTEST: Invoice creation with invalid email format (notanemail)")
        print("EXPECTED: Request fails with error message about user not existing, success=False, status=200")
        
        post_data = {
            "email": "notanemail",  # Invalid email format
            "issue_date": "2026-03-01",
            "due_date": "2026-04-01",
            "customer_notes": "Test invoice",
            "description[]": ["Service"],
            "quantity[]": ["1"],
            "unit_price[]": ["100.00"]
        }

        response = self.client.post(self.create_invoice_url, post_data)
        response_data = json.loads(response.content)
        actual_error = response_data.get("error")
        actual_success = response_data.get("success")
        actual_status = response.status_code
        print(f"ACTUAL: status={actual_status}, success={actual_success}, error='{actual_error}'")
        
        # Check response status
        self.assertEqual(response.status_code, 200)
        print("Assertion 1 PASS: response.status_code == 200")
        
        # Check that request was not successful
        self.assertFalse(response_data.get("success"))
        print("Assertion 2 PASS: response success == False")
        
        # Check exact error message
        self.assertEqual(
            actual_error,
            "User does not exist within the database, invoice has not been created."
        )
        print("Assertion 3 PASS: error message matches expected")

    def test_create_invoice_with_nonexistent_email(self):
        """
        Test that invoice creation fails when email doesn't exist in database
        """
        print("\nTEST: Invoice creation with nonexistent email (nonexistent@example.com)")
        print("EXPECTED: Request fails with error message about user not existing, success=False, status=200")
        
        post_data = {
            "email": "nonexistent@example.com",
            "issue_date": "2026-03-01",
            "due_date": "2026-04-01",
            "customer_notes": "Test invoice",
            "description[]": ["Service"],
            "quantity[]": ["1"],
            "unit_price[]": ["100.00"]
        }

        response = self.client.post(self.create_invoice_url, post_data)
        response_data = json.loads(response.content)
        actual_error = response_data.get("error")
        actual_success = response_data.get("success")
        actual_status = response.status_code
        print(f"ACTUAL: status={actual_status}, success={actual_success}, error='{actual_error}'")
        
        # Check response status
        self.assertEqual(response.status_code, 200)
        print("Assertion 1 PASS: response.status_code == 200")
        
        # Check that request was not successful
        self.assertFalse(response_data.get("success"))
        print("Assertion 2 PASS: response success == False")
        
        # Check exact error message
        self.assertEqual(
            actual_error,
            "User does not exist within the database, invoice has not been created."
        )
        print("Assertion 3 PASS: error message matches expected")

    def test_create_invoice_with_invalid_due_date(self):
        """
        Test that invoice creation fails when due date is before issue date
        """
        print("\nTEST: Invoice creation with invalid due date (due_date before issue_date)")
        print("EXPECTED: Request fails with error about invalid due date, success=False, status=200")
        
        post_data = {
            "email": "client@example.com",
            "issue_date": "2026-04-01",  # Issue date after due date
            "due_date": "2026-03-01",    # Due date before issue date
            "customer_notes": "Test invoice",
            "description[]": ["Service"],
            "quantity[]": ["1"],
            "unit_price[]": ["100.00"]
        }

        response = self.client.post(self.create_invoice_url, post_data)
        response_data = json.loads(response.content)
        actual_error = response_data.get("error")
        actual_success = response_data.get("success")
        actual_status = response.status_code
        print(f"ACTUAL: status={actual_status}, success={actual_success}, error='{actual_error}'")
        
        # Check response status
        self.assertEqual(response.status_code, 200)
        print("Assertion 1 PASS: response.status_code == 200")
        
        # Check that request was not successful
        self.assertFalse(response_data.get("success"))
        print("Assertion 2 PASS: response success == False")
        
        # Check exact error message
        self.assertEqual(
            actual_error,
            "Invalid due date, please set due date to be after the issue date."
        )
        print("Assertion 3 PASS: error message matches expected")

    def test_create_invoice_with_negative_price(self):
        """
        Test that invoice creation fails when line item has a negative price
        """
        print("\nTEST: Invoice creation with negative unit price (-50.00)")
        print("EXPECTED: Request fails with error about negative price, success=False, status=200")
        
        post_data = {
            "email": "client@example.com",
            "issue_date": "2026-03-01",
            "due_date": "2026-04-01",
            "customer_notes": "Test invoice",
            "description[]": ["Service"],
            "quantity[]": ["1"],
            "unit_price[]": ["-50.00"]  # Negative price
        }

        response = self.client.post(self.create_invoice_url, post_data)
        response_data = json.loads(response.content)
        actual_error = response_data.get("error")
        actual_success = response_data.get("success")
        actual_status = response.status_code
        print(f"ACTUAL: status={actual_status}, success={actual_success}, error='{actual_error}'")
        
        # Check response status
        self.assertEqual(response.status_code, 200)
        print("Assertion 1 PASS: response.status_code == 200")
        
        # Check that request was not successful
        self.assertFalse(response_data.get("success"))
        print("Assertion 2 PASS: response success == False")
        
        # Check exact error message
        self.assertEqual(
            actual_error,
            "Unit price must be greater than $0 and less than $99,999."
        )
        print("Assertion 3 PASS: error message matches expected")


def _make_fake_stripe_invoice():
    """Return a minimal MagicMock that satisfies the create_invoice view."""
    fake = MagicMock()
    fake.id = "inv_test"
    fake.amount_due = 10000  # $100 in cents
    fake.hosted_invoice_url = "https://stripe.com/inv_test"
    return fake


class _InvoiceTestBase(TestCase):
    """Shared setUp for invoice-related test classes."""

    def setUp(self):
        self.client = Client()
        self.create_invoice_url = reverse("admin_create_invoices")

        site = Site.objects.get_or_create(
            id=1, defaults={"name": "Test Site", "domain": "testserver"}
        )[0]
        social_app, _ = SocialApp.objects.get_or_create(
            provider="google",
            defaults={"name": "Google (test)", "client_id": "test-client-id"},
        )
        social_app.sites.add(site)

        self.admin_user = User.objects.create_user(
            email="admin@example.com",
            password="adminpass123",
            first_name="Admin",
            last_name="User",
            is_active=True,
            is_staff=True,
        )
        AdminProfile.objects.create(user=self.admin_user, hourly_rate=150.00)

        self.client_user = User.objects.create_user(
            email="client@example.com",
            password="clientpass123",
            first_name="Test",
            last_name="Client",
            is_active=True,
        )

        self.client.login(email="admin@example.com", password="adminpass123")

    def _post_invoice(self, unit_price, email=None):
        return self.client.post(
            self.create_invoice_url,
            {
                "email": email or "client@example.com",
                "issue_date": "2026-03-01",
                "due_date": "2026-04-01",
                "customer_notes": "",
                "description[]": ["Service"],
                "quantity[]": ["1"],
                "unit_price[]": [str(unit_price)],
            },
        )


class UnitPriceBoundsTests(_InvoiceTestBase):
    """LLW-263: Unit price must be > 0 and < 99,999."""

    PRICE_ERROR = "Unit price must be greater than $0 and less than $99,999."

    # --- invalid cases (no Stripe calls should be made) ---

    def test_unit_price_zero_is_invalid(self):
        response = self._post_invoice(0)
        data = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(data["success"])
        self.assertEqual(data["error"], self.PRICE_ERROR)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_unit_price_negative_is_invalid(self):
        response = self._post_invoice(-50)
        data = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(data["success"])
        self.assertEqual(data["error"], self.PRICE_ERROR)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_unit_price_99999_is_invalid(self):
        response = self._post_invoice(99999)
        data = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(data["success"])
        self.assertEqual(data["error"], self.PRICE_ERROR)
        self.assertEqual(Invoice.objects.count(), 0)

    # --- valid cases (Stripe calls mocked) ---

    @patch("finances.views.get_or_create_stripe_customer_id", return_value="cus_test")
    @patch("finances.views.stripe")
    def test_unit_price_99998_99_is_valid(self, mock_stripe, _mock_stripe_id):
        fake_inv = _make_fake_stripe_invoice()
        mock_stripe.Invoice.create.return_value = fake_inv
        mock_stripe.Invoice.finalize_invoice.return_value = fake_inv

        response = self._post_invoice(99998.99)
        data = json.loads(response.content)
        self.assertTrue(data["success"])
        self.assertEqual(Invoice.objects.count(), 1)

    @patch("finances.views.get_or_create_stripe_customer_id", return_value="cus_test")
    @patch("finances.views.stripe")
    def test_unit_price_1_is_valid(self, mock_stripe, _mock_stripe_id):
        fake_inv = _make_fake_stripe_invoice()
        mock_stripe.Invoice.create.return_value = fake_inv
        mock_stripe.Invoice.finalize_invoice.return_value = fake_inv

        response = self._post_invoice(1)
        data = json.loads(response.content)
        self.assertTrue(data["success"])
        self.assertEqual(Invoice.objects.count(), 1)


class PendingInvoiceValidationTests(_InvoiceTestBase):
    """LLW-264: Cannot create invoice when client already has a pending one."""

    PENDING_ERROR = (
        "This client already has a pending invoice. "
        "Please have the client pay it or void the pending invoice before creating a new one."
    )

    def _create_invoice(self, status):
        return Invoice.objects.create(
            user=self.client_user,
            amount=10000,
            status=status,
        )

    def test_pending_invoice_blocks_creation(self):
        self._create_invoice(Invoice.Status.PENDING)

        response = self._post_invoice(100)
        data = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(data["success"])
        self.assertEqual(data["error"], self.PENDING_ERROR)
        # Count must stay at 1 (the pre-existing pending invoice, no new one added).
        self.assertEqual(Invoice.objects.count(), 1)

    @patch("finances.views.get_or_create_stripe_customer_id", return_value="cus_test")
    @patch("finances.views.stripe")
    def test_voided_invoice_allows_creation(self, mock_stripe, _mock_stripe_id):
        self._create_invoice(Invoice.Status.VOIDED)
        fake_inv = _make_fake_stripe_invoice()
        mock_stripe.Invoice.create.return_value = fake_inv
        mock_stripe.Invoice.finalize_invoice.return_value = fake_inv

        response = self._post_invoice(100)
        data = json.loads(response.content)
        self.assertTrue(data["success"])
        # One pre-existing voided + one newly created = 2.
        self.assertEqual(Invoice.objects.count(), 2)

    @patch("finances.views.get_or_create_stripe_customer_id", return_value="cus_test")
    @patch("finances.views.stripe")
    def test_paid_invoice_allows_creation(self, mock_stripe, _mock_stripe_id):
        self._create_invoice(Invoice.Status.PAID)
        fake_inv = _make_fake_stripe_invoice()
        mock_stripe.Invoice.create.return_value = fake_inv
        mock_stripe.Invoice.finalize_invoice.return_value = fake_inv

        response = self._post_invoice(100)
        data = json.loads(response.content)
        self.assertTrue(data["success"])
        self.assertEqual(Invoice.objects.count(), 2)
