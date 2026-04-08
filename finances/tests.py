from datetime import timedelta

from django.urls import reverse
from django.utils import timezone 
from django.contrib.messages import get_messages
from django.contrib.auth import get_user_model, authenticate
from django.contrib.sites.models import Site
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime
from allauth.socialaccount.models import SocialApp

from finances.models import Invoice, Payment
from finances.views import get_or_create_stripe_customer_id
from users.models import AdminProfile
from decimal import Decimal

import logging
import stripe
import json
import uuid

User = get_user_model()



class AdminTransactionsViewTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="adminpass",
            first_name="Admin",
            last_name="User",
            is_staff=True,
            is_active=True,
        )
        self.client_user = User.objects.create_user(
            email="client@example.com",
            password="clientpass",
            first_name="Client",
            last_name="User",
            is_active=True,
        )
        self.url = reverse("admin_transactions")

    def _make_invoices(self, count):
        Invoice.objects.bulk_create([
            Invoice(user=self.client_user, amount=(i + 1) * 100, status=Invoice.Status.PENDING)
            for i in range(count)
        ])

    def _make_invoices_with_timestamps(self, count):
        """
        Create `count` invoices with deterministic, unique created_at values.
        The invoice with the highest PK (last created) gets the most recent timestamp.
        Returns the invoices ordered by -created_at (most recent first).
        """
        base_time = timezone.now()
        Invoice.objects.bulk_create([
            Invoice(user=self.client_user, amount=(i + 1) * 100, status=Invoice.Status.PENDING)
            for i in range(count)
        ])
        # Order by pk to assign timestamps oldest-first; last pk = most recent.
        for idx, pk in enumerate(Invoice.objects.order_by("pk").values_list("pk", flat=True)):
            Invoice.objects.filter(pk=pk).update(
                created_at=base_time - timedelta(minutes=(count - 1 - idx))
            )
        return Invoice.objects.order_by("-created_at")

    # ------------------------------------------------------------------ #
    # A) Authentication / Authorization                                    #
    # ------------------------------------------------------------------ #

    def test_unauthenticated_user_forbidden(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_requires_admin(self):
        self.client.force_login(self.client_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    # ------------------------------------------------------------------ #
    # B) Pagination default + ordering                                     #
    # ------------------------------------------------------------------ #

    def test_default_returns_20_invoices_per_page(self):
        self._make_invoices(25)
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"]), 20)
        self.assertEqual(response.context["per_page"], 20)

    def test_invoices_ordered_most_recent_first(self):
        """
        Seed 55 invoices with deterministic timestamps.
        Page 1 must contain exactly 20 items sorted most-recent-first,
        and the very first item must be the newest invoice overall.
        """
        ordered = self._make_invoices_with_timestamps(55)
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        page_items = list(response.context["page_obj"])
        self.assertEqual(len(page_items), 20)

        # Items on the page must be sorted descending by created_at.
        dates = [inv.created_at for inv in page_items]
        self.assertEqual(dates, sorted(dates, reverse=True))

        # The first item on page 1 must be the newest invoice in the DB.
        newest = ordered.first()
        self.assertEqual(page_items[0].pk, newest.pk)

    # ------------------------------------------------------------------ #
    # C) Per-page selection                                                #
    # ------------------------------------------------------------------ #

    def test_per_page_40_returns_40_invoices(self):
        self._make_invoices(45)
        self.client.force_login(self.admin)
        response = self.client.get(self.url, {"per_page": "40"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"]), 40)
        self.assertEqual(response.context["per_page"], 40)

    def test_invalid_per_page_falls_back_to_20(self):
        """per_page=999 (not in allowed set) falls back to default 20."""
        self._make_invoices(25)
        self.client.force_login(self.admin)
        response = self.client.get(self.url, {"per_page": "999"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["per_page"], 20)
        self.assertEqual(len(response.context["page_obj"]), 20)

    def test_invalid_per_page_zero_falls_back_to_20(self):
        """per_page=0 falls back to default 20."""
        self._make_invoices(25)
        self.client.force_login(self.admin)
        response = self.client.get(self.url, {"per_page": "0"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["per_page"], 20)

    def test_invalid_per_page_string_falls_back_to_20(self):
        """Non-numeric per_page falls back to default 20."""
        self._make_invoices(25)
        self.client.force_login(self.admin)
        response = self.client.get(self.url, {"per_page": "abc"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["per_page"], 20)

    # ------------------------------------------------------------------ #
    # D) Pagination navigation                                             #
    # ------------------------------------------------------------------ #

    def test_pagination_has_multiple_pages_when_over_20(self):
        self._make_invoices(25)
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["page_obj"].has_other_pages())
        self.assertEqual(response.context["page_obj"].paginator.num_pages, 2)

    def test_page_2_returns_remaining_invoices(self):
        self._make_invoices(25)
        self.client.force_login(self.admin)
        response = self.client.get(self.url, {"page": "2"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"]), 5)

    def test_page_2_does_not_overlap_with_page_1(self):
        """With 55 invoices, page 1 and page 2 must not share any invoice IDs."""
        self._make_invoices_with_timestamps(55)
        self.client.force_login(self.admin)
        response_p1 = self.client.get(self.url)
        response_p2 = self.client.get(self.url, {"page": "2"})
        self.assertEqual(response_p1.status_code, 200)
        self.assertEqual(response_p2.status_code, 200)

        ids_p1 = {inv.pk for inv in response_p1.context["page_obj"]}
        ids_p2 = {inv.pk for inv in response_p2.context["page_obj"]}
        self.assertEqual(len(ids_p1), 20)
        self.assertEqual(len(ids_p2), 20)
        self.assertFalse(ids_p1 & ids_p2, "Page 1 and Page 2 must not share any invoices")

    # ------------------------------------------------------------------ #
    # E) UI markers                                                        #
    # ------------------------------------------------------------------ #

    def test_html_per_page_select_exists_with_options(self):
        """The results-per-page control must be rendered with 20 and 40 options."""
        self._make_invoices(25)
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('name="per_page"', content)
        self.assertIn('value="20"', content)
        self.assertIn('value="40"', content)

    def test_html_pagination_controls_render(self):
        """With >20 invoices, Next link and pagination list must appear in HTML."""
        self._make_invoices(25)
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Next", content)
        self.assertIn('class="pagination', content)

    # ------------------------------------------------------------------ #
    # Display helpers                                                      #
    # ------------------------------------------------------------------ #

    def test_display_helpers_attached_to_page_items(self):
        self._make_invoices(1)
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        inv = list(response.context["page_obj"])[0]
        self.assertTrue(hasattr(inv, "amount_dollars"))
        self.assertTrue(hasattr(inv, "display_status"))
        self.assertEqual(inv.display_status, "PENDING")

class ClientTransactionsViewTest(TestCase):
    def setUp(self):
        # Create test user
        self.client_user = User.objects.create_user(
            email='client@example.com',
            password='testpass123',
            first_name='Test',
            last_name='Client',
            role=User.Role.CLIENT
        )
        self.client_user.is_active = True
        self.client_user.save()
        
        # Create test client
        self.client = Client()
        
        # Store the URL for reuse
        self.invoices_url = reverse('client_invoices')

    def create_test_invoices(self):
        base_time = timezone.now()

        # Create current (pending) invoice with Stripe URL
        self.current_invoice = Invoice.objects.create(
            user=self.client_user,
            amount=50000,  # $500.00
            status=Invoice.Status.PENDING,
            hosted_invoice_url='https://invoice.stripe.com/i/test_invoice_123'
        )
        Invoice.objects.filter(pk=self.current_invoice.pk).update(
            created_at=base_time - timedelta(days=1)
        )
        self.current_invoice.refresh_from_db()

        # Create 12 past invoices (paid), then force deterministic timestamps via update()
        # so auto_now_add is bypassed. i=0 is most recent (now-2d), i=11 is oldest (now-13d).
        for i in range(12):
            inv = Invoice.objects.create(
                user=self.client_user,
                amount=25000 + (i * 1000),
                status=Invoice.Status.PAID,
            )
            Invoice.objects.filter(pk=inv.pk).update(
                created_at=base_time - timedelta(days=i + 2)
            )

    # Test unauthenticated users are redirected to login
    def test_requires_authentication(self):
        # Try to access without logging in
        response = self.client.get(self.invoices_url)
        
        # Should redirect to login page
        expected_url = f"{reverse('login')}?next={self.invoices_url}"
        self.assertRedirects(response, expected_url)
        
        # Log in and verify access works
        self.client.login(username='client@example.com', password='testpass123')
        response = self.client.get(self.invoices_url)
        self.assertEqual(response.status_code, 200)

    
    # Test that only the 10 most recent past invoices are displayed
    def test_shows_10_most_recent_transactions(self):
        # Create test invoices
        self.create_test_invoices()
        
        # Log in
        self.client.login(username='client@example.com', password='testpass123')
        
        # Get the page
        response = self.client.get(self.invoices_url)
        
        # Check that past_invoices is in context
        self.assertIn('past_invoices', response.context)
        past_invoices = response.context['past_invoices']
        
        # Should have exactly 10 past invoices (limited to 10)
        self.assertEqual(len(past_invoices), 10)
        
        # Verify they are the most recent ones (excluding current)
        all_past = Invoice.objects.filter(
            user=self.client_user).exclude(id=self.current_invoice.id).order_by('-created_at')
        
        # The 10 most recent should match what's in context
        self.assertEqual(
            [inv.id for inv in past_invoices],
            [inv.id for inv in all_past[:10]]
        )

    # Test that every transaction shows amount, date, and status
    def test_displays_amount_date_status_for_each_transaction(self):
        # Create test invoices
        self.create_test_invoices()
        
        # Log in
        self.client.login(username='client@example.com', password='testpass123')
        
        # Get the page
        response = self.client.get(self.invoices_url)
        
        # First, verify the context data is correct
        self.assertIn('current_invoice', response.context)
        self.assertIn('past_invoices', response.context)
        self.assertIn('stripe_url', response.context)
        
        current = response.context['current_invoice']
        past_invoices = response.context['past_invoices']
        
        # Verify current invoice has all required fields in context
        self.assertEqual(current.display_amount, Decimal('500.00'))
        self.assertIsNotNone(current.created_at)
        self.assertEqual(current.status, Invoice.Status.PENDING)
        self.assertEqual(response.context['stripe_url'], 'https://invoice.stripe.com/i/test_invoice_123')
        
        # Verify past invoices have all required fields in context
        for invoice in past_invoices:
            expected_amount = invoice.amount / 100
            self.assertEqual(invoice.display_amount, expected_amount)
            self.assertIsNotNone(invoice.created_at)
            self.assertEqual(invoice.status, Invoice.Status.PAID)
        
        # Check the HTML content
        content = response.content.decode()
        
        # Check that current invoice data appears in HTML
        self.assertIn('$500.00', content)
        self.assertIn('Pending', content)
        self.assertIn('https://invoice.stripe.com/i/test_invoice_123', content)
        
        # Check that a sample of past invoices data appears
        self.assertIn('$250.00', content)  # First past invoice
        self.assertIn('$260.00', content)  # Second past invoice
        self.assertIn('Paid', content)  # Status appears multiple times
    

class GuestInvoiceIdValidationTests(TestCase):
    def _messages(self, response):
        return [m.message for m in get_messages(response.wsgi_request)]

    def test_payment_post_with_invalid_invoice_id_shows_error(self):
        url = reverse("payment")
        resp = self.client.post(url, data={"invoice_id": "999999"}, follow=True)
        self.assertEqual(resp.status_code, 404)
        self.assertIn("Incorrect/Invalid Invoice ID.", self._messages(resp))

    def test_payment_post_with_valid_invoice_number_redirects_to_checkout(self):
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
            stripe_invoice_number="ABCDEFGH-0001",
        )

        url = reverse("payment")
        resp = self.client.post(url, data={"invoice_id": inv.stripe_invoice_number})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("create_checkout_session", args=[inv.stripe_invoice_number]))

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
    fake.number = "ABCDEFGH-0001"
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


class StripePaymentFlowTests(TestCase):
    """Test the actual Stripe payment processing flow"""

    def setUp(self):
        self.user = User.objects.create_user(
            email="client@example.com",
            password="testpass",
            first_name="Test",
            last_name="Client",
            is_active=True,
        )
        self.invoice = Invoice.objects.create(
            user=self.user,
            amount=50000,  # $500
            status=Invoice.Status.PENDING,
            hosted_invoice_url="https://stripe.com/test_invoice"
        )

    ############################### Order Summary Display Tests ###############################

    # Test: Payment page for logged-in users shows order summary
    def test_payment_page_for_logged_in_users_shows_order_summary(self):
        """Payment page for logged-in users shows order summary"""
        print("\nTEST: Payment page for logged-in users shows order summary")
        print("EXPECTED: Page loads with status=200, shows correct amount, Amount Due, Pay Now, Status: Pending")
        
        self.client.force_login(self.user)
        response = self.client.get(reverse('client_invoices'))

        # Should show current invoice with correct amount.
        expected_display_amount = f"${self.invoice.amount / 100:.2f}"  # Convert cents to dollars.
        print(f"ACTUAL: status={response.status_code}, amount_displayed={expected_display_amount}")

        self.assertEqual(response.status_code, 200) # Assert success code.
        print("Assertion 1 PASS: response.status_code == 200")

        # Ensure the invoice details are displayed correctly for a pending order.
        self.assertContains(response, expected_display_amount)
        print("Assertion 2 PASS: expected_display_amount in response")
        self.assertContains(response, 'Amount Due')
        print("Assertion 3 PASS: 'Amount Due' in response")
        self.assertContains(response, 'Pay Now')
        print("Assertion 4 PASS: 'Pay Now' in response")
        self.assertContains(response, 'Status: Pending')
        print("Assertion 5 PASS: 'Status: Pending' in response")
        
    # Test: Payment page shows correct amount regardless of invoice amount
    def test_payment_page_shows_correct_amount_for_different_invoice_amounts(self):
        """Payment page shows correct amount regardless of invoice amount"""
        # Test with different amounts to ensure the display is dynamic.
        test_amounts = [10000, 25000, 75000, 100000]  # $100, $250, $750, $1000.

        for amount in test_amounts:
            with self.subTest(amount=amount):
                print(f"\nTEST: Payment page shows correct amount for invoice amount {amount} (${amount/100:.2f})")
                print(f"EXPECTED: Page loads with status=200, shows amount ${amount/100:.2f}")
                
                # Update the invoice amount.
                self.invoice.amount = amount
                self.invoice.save()

                self.client.force_login(self.user)
                response = self.client.get(reverse('client_invoices'))
                self.assertEqual(response.status_code, 200)

                # Should show the correct amount for this invoice.
                expected_display_amount = f"${amount / 100:.2f}"

                print(f"ACTUAL: status={response.status_code}, amount_displayed={expected_display_amount}")
                print("Assertion 1 PASS: response.status_code == 200")

                # Ensure the invoice details are the proper displayed values.
                self.assertContains(response, expected_display_amount)
                print("Assertion 2 PASS: expected_display_amount in response")
                self.assertContains(response, 'Amount Due')
                print("Assertion 3 PASS: 'Amount Due' in response")
                self.assertContains(response, 'Pay Now')
                print("Assertion 4 PASS: 'Pay Now' in response")
                
    ############################### Checkout Session Tests ###############################

    # Test: Checkout session creation requires valid invoice
    def test_checkout_session_creation_requires_valid_invoice(self):
        """Checkout session creation requires valid invoice"""
        print("\nTEST: Checkout session creation with invalid invoice ID (99999)")
        print("EXPECTED: Request redirects with status=302 to payment page")
        
        # Test with invalid invoice ID.
        response = self.client.get(reverse('create_checkout_session', args=[99999]))
        print(f"ACTUAL: status={response.status_code}")

        self.assertEqual(response.status_code, 302) # Error code that is sent by Django redirect().
        print("Assertion 1 PASS: response.status_code == 302")
        self.assertRedirects(response, reverse('payment'))    
        print("Assertion 2 PASS: redirects to payment page")

    ############################### Stripe Customer Management Tests ###############################

    # Test: User's Stripe customer ID is created/reused
    @patch("finances.views.stripe")
    def test_user_stripe_customer_id_created_and_reused(self, mock_stripe):
        """User's Stripe customer ID is created/reused"""
        print("\nTEST: User's Stripe customer ID is created and reused")
        print("EXPECTED: First call creates customer, second call reuses existing ID")
        
        # Mock Stripe customer creation.
        mock_customer = MagicMock()
        mock_customer.id = "cus_test123"
        mock_stripe.Customer.create.return_value = mock_customer

        # First call should create customer.
        customer_id = get_or_create_stripe_customer_id(self.user)
        self.assertEqual(customer_id, "cus_test123")
        mock_stripe.Customer.create.assert_called_once()
        
        # Refresh user from DB.
        self.user.refresh_from_db()
        self.assertEqual(self.user.provider_customer_id, "cus_test123")

        # Second call should reuse existing ID.
        mock_stripe.Customer.create.reset_mock()
        customer_id2 = get_or_create_stripe_customer_id(self.user)
        self.assertEqual(customer_id2, "cus_test123")
        mock_stripe.Customer.create.assert_not_called()  # Should not create again.
        
        print(f"ACTUAL: first_customer_id={customer_id}, second_customer_id={customer_id2}")
        print("Assertion 1 PASS: customer_id == 'cus_test123'")
        print("Assertion 2 PASS: mock_stripe.Customer.create.assert_called_once()")
        print("Assertion 3 PASS: self.user.provider_customer_id == 'cus_test123'")
        print("Assertion 4 PASS: customer_id2 == 'cus_test123'")
        print("Assertion 5 PASS: mock_stripe.Customer.create.assert_not_called()")

    ############################### Payment Processing Tests ###############################

    # Test: Successful payment updates invoice status to PAID
    @patch("finances.views.stripe")
    def test_successful_payment_updates_invoice_status_to_paid(self, mock_stripe):
        """Successful payment updates invoice status to PAID"""
        print("\nTEST: Successful payment updates invoice status to PAID")
        print("EXPECTED: Checkout session created (302), webhook processed (200), invoice status becomes PAID")
        
        # Mock Stripe checkout session for testing uses.
        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/test"
        mock_stripe.checkout.Session.create.return_value = mock_session

        # Create checkout session.
        checkout_response = self.client.get(reverse('create_checkout_session', args=[self.invoice.id]))
        self.assertEqual(checkout_response.status_code, 302)

        # Simulate webhook for successful payment.
        webhook_data = {
            "id": "evt_test",
            "type": "invoice.paid",
            "data": {
                "object": {
                    "id": "inv_test",
                    "metadata": {"invoice_id": str(self.invoice.id)},
                    "status": "paid"
                }
            }
        }

        # Mock webhook signature verification.
        # I didn't even know you could do this, this was a very cool find.
        with patch("finances.views.stripe.Webhook.construct_event", return_value=webhook_data), \
             patch("finances.views.settings.STRIPE_WEBHOOK_SECRET", "test_secret"):
            webhook_response = self.client.post(
                reverse('stripe_webhook'),
                data=json.dumps(webhook_data),
                content_type='application/json',
                HTTP_STRIPE_SIGNATURE='test_sig'
            )
            self.assertEqual(webhook_response.status_code, 200)

        # Check invoice was updated.
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)
        self.assertTrue(self.invoice.paid)
        
        print(f"ACTUAL: checkout_status={checkout_response.status_code}, webhook_status={webhook_response.status_code}, final_invoice_status={self.invoice.status}")
        print("Assertion 1 PASS: checkout response.status_code == 302")
        print("Assertion 2 PASS: webhook response.status_code == 200")
        print("Assertion 3 PASS: self.invoice.status == Invoice.Status.PAID")
        print("Assertion 4 PASS: self.invoice.paid == True")

    # Test: Payment creates Payment record in DB
    @patch("finances.views.stripe")
    def test_payment_creates_payment_record_in_db(self, mock_stripe):
        """Payment creates Payment record in DB"""
        print("\nTEST: Payment creates Payment record in DB")
        print("EXPECTED: Webhook processed (200), Payment record created with correct details")

        # Simulate webhook for successful payment.
        webhook_data = {
            "id": "evt_test",
            "type": "invoice.paid", 
            "data": {
                "object": {
                    "id": "inv_test",
                    "amount_due": 50000,
                    "metadata": {"invoice_id": str(self.invoice.id)},
                    "status": "paid"
                }
            }
        }

        # Count payments before.
        initial_payment_count = Payment.objects.count()

        # Mock webhook signature verification.
        with patch("finances.views.stripe.Webhook.construct_event", return_value=webhook_data), \
             patch("finances.views.settings.STRIPE_WEBHOOK_SECRET", "test_secret"):
            response = self.client.post(
                reverse('stripe_webhook'),
                data=json.dumps(webhook_data),
                content_type='application/json',
                HTTP_STRIPE_SIGNATURE='test_sig'
            )
            self.assertEqual(response.status_code, 200)

        # Check that Payment record was created.
        final_payment_count = Payment.objects.count()
        self.assertEqual(final_payment_count, initial_payment_count + 1)
        
        payment = Payment.objects.latest('id')
        self.assertEqual(payment.user, self.user)
        self.assertEqual(payment.amount, 50000)
        self.assertEqual(payment.status, Payment.Status.SUCCESS)
        
        print(f"ACTUAL: webhook_status={response.status_code}, initial_count={initial_payment_count}, final_count={final_payment_count}, payment_user={payment.user}, payment_amount={payment.amount}, payment_status={payment.status}")
        print("Assertion 1 PASS: response.status_code == 200")
        print("Assertion 2 PASS: final_payment_count == initial_payment_count + 1")
        print("Assertion 3 PASS: payment.user == self.user")
        print("Assertion 4 PASS: payment.amount == 50000")
        print("Assertion 5 PASS: payment.status == Payment.Status.SUCCESS")

# Admin is able to change client balances by voiding pending invoice and creating a new one
class AdminChangeClientBalanceTest(TestCase):
    # Return a minimal MagicMock that satisfies the create_invoice view
    @staticmethod
    def mock_invoice(invoice_id="inv_test", amount_due=10000, hosted_url="https://stripe.com/invoice/test"):
        mock_invoice = MagicMock()
        mock_invoice.id = invoice_id
        mock_invoice.number = f"ABCDEFGH-{invoice_id.split('_')[-1]}"
        mock_invoice.amount_due = amount_due
        mock_invoice.hosted_invoice_url = hosted_url
        # Add the .get() method that the admin_stripe_invoice_detail expects
        mock_invoice.get = MagicMock(side_effect=lambda key: {
            "id": mock_invoice.id,
            "number": mock_invoice.number,
            "amount_due": mock_invoice.amount_due,
            "hosted_invoice_url": mock_invoice.hosted_invoice_url,
            "status": "open",
            "currency": "usd",
            "customer": "cus_test123",
        }.get(key))
        return mock_invoice

    def setUp(self):
        self.client = Client()
        self.create_invoice_url = reverse("admin_create_invoices")
        
        # Create admin user with proper permissions
        self.admin_user = User.objects.create_user(
            email="admin@example.com",
            password="adminpass",
            first_name="Admin",
            last_name="User",
            is_active=True,
            is_staff=True,
        )
        
        # Create regular user (client)
        self.client_user = User.objects.create_user(
            email="client@example.com",
            password="clientpass",
            first_name="Client",
            last_name="User",
            provider_customer_id="cus_test123",
            is_active=True
        )
        
        # Login as admin
        self.client.login(email="admin@example.com", password="adminpass")
    
    # Helper to create a test invoice
    def create_test_invoice(self, status="PENDING", amount=10000, stripe_invoice_id=None):
        if not stripe_invoice_id:
            stripe_invoice_id = f"inv_test_{str(uuid.uuid4())[:8]}"
        
        invoice = Invoice.objects.create(
            user=self.client_user,
            amount=amount,
            stripe_invoice_id=stripe_invoice_id,
            hosted_invoice_url="https://stripe.com/invoice/test",
            status=status,
        )
        
        if status == "PAID":
            invoice.paid = True
            invoice.save()
        
        return invoice

    # Test successfully voiding a pending invoice
    def test_void_pending_invoice_success(self):
        invoice = self.create_test_invoice(status="PENDING")
        
        with patch("finances.views.stripe") as mock_stripe:
            mock_stripe.Invoice.void_invoice.return_value = MagicMock()
            
            url = f'/api/admin/stripe/invoice/{invoice.stripe_invoice_id}/void/'
            response = self.client.post(url)
            
            self.assertEqual(response.status_code, 200)
            response_data = json.loads(response.content)
            self.assertEqual(response_data["status"], "voided")
            
            invoice.refresh_from_db()
            self.assertEqual(invoice.status, Invoice.Status.VOIDED)
            self.assertFalse(invoice.paid)
            
            mock_stripe.Invoice.void_invoice.assert_called_once_with(
                invoice.stripe_invoice_id
            )

    # Test attempting to void an already voided invoice
    def test_void_already_voided_invoice(self):    
        invoice = self.create_test_invoice(status="VOIDED")
        
        url = f'/api/admin/stripe/invoice/{invoice.stripe_invoice_id}/void/'
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 400)
        response_data = json.loads(response.content)
        self.assertEqual(response_data["error"], "Invoice is already voided")

    # Test attempting to void a paid invoice
    def test_void_paid_invoice(self):
        invoice = self.create_test_invoice(status="PAID")
        
        url = f'/api/admin/stripe/invoice/{invoice.stripe_invoice_id}/void/'
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 400)
        response_data = json.loads(response.content)
        self.assertEqual(response_data["error"], "Cannot void a paid invoice")

    # Test creating a new invoice after voiding the old one
    @patch("finances.views.stripe")
    def test_create_new_invoice_after_void(self, mock_stripe):
        
        # Create initial invoice
        invoice = self.create_test_invoice(status="PENDING")
        
        # Mock void operation
        mock_stripe.Invoice.void_invoice.return_value = MagicMock()
        
        void_url = f'/api/admin/stripe/invoice/{invoice.stripe_invoice_id}/void/'
        void_response = self.client.post(void_url)
        self.assertEqual(void_response.status_code, 200)
        
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.VOIDED)
        
        # Create mock invoice using the helper method
        mock_invoice = self.mock_invoice(
            invoice_id="inv_test_456",
            amount_due=15000,
            hosted_url="https://stripe.com/invoice/test2"
        )
        
        mock_stripe.Invoice.create.return_value = mock_invoice
        mock_stripe.Invoice.finalize_invoice.return_value = mock_invoice
        mock_stripe.Customer.create.return_value = MagicMock(id="cus_test123")
        mock_stripe.InvoiceItem.create.return_value = MagicMock()
        
        post_data = {
            "email": self.client_user.email,
            "issue_date": "2026-04-10",
            "due_date": "2026-05-10",
            "customer_notes": "Updated invoice after void",
            "description[]": ["Legal Consultation", "Document Review"],
            "quantity[]": ["1", "2"],
            "unit_price[]": ["100.00", "50.00"]
        }
        
        response = self.client.post(self.create_invoice_url, post_data)
        
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertTrue(response_data["success"])
        
        new_invoices = Invoice.objects.filter(user=self.client_user, status="PENDING")
        self.assertEqual(new_invoices.count(), 1)
        
        new_invoice = new_invoices.first()
        self.assertNotEqual(new_invoice.id, invoice.id)

    # Test that creating a new invoice after void doesn't conflict with pending
    @patch("finances.views.stripe")
    def test_create_invoice_after_void_prevents_pending_conflict(self, mock_stripe):
        
        # Create a pending invoice
        pending_invoice = self.create_test_invoice(status="PENDING")
        
        post_data = {
            "email": self.client_user.email,
            "issue_date": "2026-04-10",
            "due_date": "2026-05-10",
            "customer_notes": "Should be blocked",
            "description[]": ["Service"],
            "quantity[]": ["1"],
            "unit_price[]": ["100.00"]
        }
        
        # First attempt - should be blocked
        response = self.client.post(self.create_invoice_url, post_data)
        
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertFalse(response_data["success"])
        self.assertIn("already has a pending invoice", response_data["error"])
        
        # Mock void operation
        mock_stripe.Invoice.void_invoice.return_value = MagicMock()
        
        void_url = f'/api/admin/stripe/invoice/{pending_invoice.stripe_invoice_id}/void/'
        void_response = self.client.post(void_url)
        self.assertEqual(void_response.status_code, 200)
        
        pending_invoice.refresh_from_db()
        self.assertEqual(pending_invoice.status, Invoice.Status.VOIDED)
        
        # Create mock invoice using the helper method
        mock_invoice = self.mock_invoice(
            invoice_id="inv_new_789",
            amount_due=10000,
            hosted_url="https://stripe.com/invoice/new"
        )
        
        mock_stripe.Invoice.create.return_value = mock_invoice
        mock_stripe.Invoice.finalize_invoice.return_value = mock_invoice
        mock_stripe.Customer.create.return_value = MagicMock(id="cus_test123")
        mock_stripe.InvoiceItem.create.return_value = MagicMock()
        
        # Second attempt - should succeed
        response = self.client.post(self.create_invoice_url, post_data)
        
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertTrue(response_data["success"])

    # Test the complete flow: create -> void -> create new invoice
    @patch("finances.views.stripe")
    def test_complete_void_and_recreate_flow(self, mock_stripe):
        # Step 1: Create initial invoice
        initial_post_data = {
            "email": self.client_user.email,
            "issue_date": "2026-04-10",
            "due_date": "2026-05-10",
            "customer_notes": "Initial invoice",
            "description[]": ["Service A", "Service B"],
            "quantity[]": ["1", "2"],
            "unit_price[]": ["100.00", "75.00"]
        }
        
        # Create mock invoice using the helper method
        mock_initial_invoice = self.mock_invoice(
            invoice_id="inv_initial_123",
            amount_due=25000,
            hosted_url="https://stripe.com/invoice/initial"
        )
        
        mock_stripe.Invoice.create.return_value = mock_initial_invoice
        mock_stripe.Invoice.finalize_invoice.return_value = mock_initial_invoice
        mock_stripe.Customer.create.return_value = MagicMock(id="cus_test123")
        mock_stripe.InvoiceItem.create.return_value = MagicMock()
        
        response = self.client.post(self.create_invoice_url, initial_post_data)
        
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertTrue(response_data["success"])
        
        initial_invoice = Invoice.objects.get(stripe_invoice_id="inv_initial_123")
        self.assertEqual(initial_invoice.status, Invoice.Status.PENDING)
        self.assertEqual(initial_invoice.amount, 25000)
        
        # Step 2: Void the initial invoice
        mock_stripe.Invoice.void_invoice.return_value = MagicMock()
        
        void_url = f'/api/admin/stripe/invoice/{initial_invoice.stripe_invoice_id}/void/'
        void_response = self.client.post(void_url)
        self.assertEqual(void_response.status_code, 200)
        
        initial_invoice.refresh_from_db()
        self.assertEqual(initial_invoice.status, Invoice.Status.VOIDED)
        
        # Step 3: Create updated invoice
        updated_post_data = {
            "email": self.client_user.email,
            "issue_date": "2026-04-15",
            "due_date": "2026-05-15",
            "customer_notes": "Updated invoice after void",
            "description[]": ["Service A (Revised)", "Service B", "Service C"],
            "quantity[]": ["1", "2", "1"],
            "unit_price[]": ["100.00", "75.00", "50.00"]
        }
        
        # Create mock invoice using the helper method
        mock_updated_invoice = self.mock_invoice(
            invoice_id="inv_updated_456",
            amount_due=30000,
            hosted_url="https://stripe.com/invoice/updated"
        )
        
        mock_stripe.Invoice.create.return_value = mock_updated_invoice
        mock_stripe.Invoice.finalize_invoice.return_value = mock_updated_invoice
        
        response = self.client.post(self.create_invoice_url, updated_post_data)
        
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertTrue(response_data["success"])
        
        updated_invoice = Invoice.objects.get(stripe_invoice_id="inv_updated_456")
        self.assertEqual(updated_invoice.status, Invoice.Status.PENDING)
        self.assertEqual(updated_invoice.amount, 30000)
        
        # Verify both invoices exist with correct statuses
        all_invoices = Invoice.objects.filter(user=self.client_user).order_by('created_at')
        self.assertEqual(all_invoices.count(), 2)
        self.assertEqual(all_invoices[0].status, Invoice.Status.VOIDED)
        self.assertEqual(all_invoices[1].status, Invoice.Status.PENDING)

class ClientInvoiceTests(TestCase):
    
    def setUp(self):
        self.client = Client()
        
        # Create a regular user (client)
        self.client_user = User.objects.create_user(
            email="client@example.com",
            password="clientpass123",
            first_name="Test",
            last_name="Client",
            is_active=True
        )
        
        # Login as the client
        self.client.login(email="client@example.com", password="clientpass123")
        
        # Get URL names (update these to match your actual URLs)
        self.invoices_url = reverse('client_invoices')
        self.payment_url = reverse('payment')  # Your payment page URL
        self.checkout_url_name = 'create_checkout_session'
        self.stripe_webhook_url = reverse('stripe_webhook')
        
    # Helper to create an invoice
    def create_invoice(self, user, status="PENDING", amount=50000, created_days_ago=0, paid=False):
        
        created_at = timezone.now() - timedelta(days=created_days_ago)
        
        invoice = Invoice.objects.create(
            user=user,
            amount=amount,
            status=status,
            paid=paid or (status == "PAID"),
            stripe_invoice_id=f"inv_test_{status}_{amount}_{created_days_ago}",
            stripe_invoice_number=f"ABCDEFGH-0001",
            hosted_invoice_url=f"https://stripe.com/invoice/test_{status}_{amount}",
            created_at=created_at
        )
        return invoice
    
    # Test that the correct pending invoice amount is displayed
    def test_pending_invoice_shows_correct_amount(self):
        
        # Create a pending invoice for $500.00
        pending_invoice = self.create_invoice(
            user=self.client_user,
            status="PENDING",
            amount=50000,
            paid=False
        )
        
        response = self.client.get(self.invoices_url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check current invoice is in context
        current_invoice = response.context.get('current_invoice')
        self.assertIsNotNone(current_invoice)
        self.assertEqual(current_invoice.id, pending_invoice.id)
        
        # Verify amount conversion from cents to dollars
        self.assertEqual(current_invoice.display_amount, 500.00)
        
        # Verify HTML contains the correct amount
        self.assertContains(response, "$500.00")
        self.assertContains(response, "Amount Due: $500.00")
        
        # Verify Pay Now button exists
        self.assertContains(response, "Pay Now")
        self.assertContains(response, pending_invoice.hosted_invoice_url)
    
    # Test when no pending invoice exists (shows past invoices only)
    def test_no_pending_invoice_shows_empty_state(self):
        
        # Create only paid invoices
        self.create_invoice(user=self.client_user, status="PAID", amount=50000, paid=True)
        
        response = self.client.get(self.invoices_url)
        
        current_invoice = response.context.get('current_invoice')
        self.assertIsNone(current_invoice)
        
        # The current invoice section should be empty (no Pay Now button)
        self.assertNotContains(response, "Pay Now")
        
        # But past invoices should still show
        self.assertContains(response, "Past Invoices")
        self.assertContains(response, "$500.00")
        self.assertContains(response, "Status: Paid")

    # Test that clicking Pay Now redirects to Stripe checkout
    @patch("finances.views.stripe")
    def test_pay_now_redirects_to_stripe_checkout(self, mock_stripe):
        
        # Create pending invoice
        invoice = self.create_invoice(
            user=self.client_user,
            status="PENDING",
            amount=50000,
            paid=False
        )
        
        # Mock Stripe checkout session
        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/session_123abc"
        mock_stripe.checkout.Session.create.return_value = mock_session
        
        # Get checkout session URL using the customer-facing invoice number
        checkout_url = reverse(self.checkout_url_name, args=[invoice.stripe_invoice_number])
        response = self.client.get(checkout_url)
        
        # Should redirect to Stripe
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "https://checkout.stripe.com/session_123abc")
        
        # Verify Stripe was called with correct parameters
        mock_stripe.checkout.Session.create.assert_called_once()
        call_kwargs = mock_stripe.checkout.Session.create.call_args[1]
        
        # Check invoice amount (should be in cents)
        line_item = call_kwargs['line_items'][0]
        self.assertEqual(line_item['price_data']['unit_amount'], 50000)
        
        # Check metadata contains the customer-facing invoice number
        self.assertEqual(call_kwargs['metadata']['invoice_id'], invoice.stripe_invoice_number)

    # Test that database reflects payment: invoice marked PAID
    @patch("finances.views.stripe")
    def test_database_updates_after_successful_payment(self, mock_stripe):
        
        # Create pending invoice
        invoice = self.create_invoice(
            user=self.client_user,
            status="PENDING",
            amount=50000,
            paid=False
        )
        
        # Verify initial state
        self.assertEqual(invoice.status, "PENDING")
        self.assertFalse(invoice.paid)
        
        # Simulate Stripe webhook for successful payment
        webhook_data = {
            "id": "evt_test_123",
            "type": "invoice.paid",
            "data": {
                "object": {
                    "id": "inv_stripe_123",
                    "amount_due": 50000,
                    "metadata": {"invoice_id": str(invoice.id)},
                    "status": "paid"
                }
            }
        }
        
        # Mock webhook verification
        with patch("finances.views.stripe.Webhook.construct_event", return_value=webhook_data), \
             patch("finances.views.settings.STRIPE_WEBHOOK_SECRET", "test_secret"):
            response = self.client.post(
                self.stripe_webhook_url,
                data=json.dumps(webhook_data),
                content_type='application/json',
                HTTP_STRIPE_SIGNATURE='test_sig'
            )
            self.assertEqual(response.status_code, 200)
        
        # Refresh invoice from database
        invoice.refresh_from_db()
        
        # Verify invoice is now marked as paid
        self.assertEqual(invoice.status, "PAID")
        self.assertTrue(invoice.paid)
        
        # Verify payment record was created
        payment = Payment.objects.filter(user=self.client_user).first()
        self.assertIsNotNone(payment)
        self.assertEqual(payment.amount, 50000)
        self.assertEqual(payment.status, "SUCCESS")
    
    # Test that invoice page shows updated status after payment
    @patch("finances.views.stripe")
    def test_invoice_page_updates_after_payment(self, mock_stripe):
        
        # Create pending invoice
        invoice = self.create_invoice(
            user=self.client_user,
            status="PENDING",
            amount=50000,
            paid=False
        )
        
        # Step 1: Before payment - invoice shows as current
        response_before = self.client.get(self.invoices_url)
        current_invoice_before = response_before.context.get('current_invoice')
        self.assertIsNotNone(current_invoice_before)
        self.assertContains(response_before, "Pay Now")
        
        # Step 2: Simulate successful payment via webhook
        webhook_data = {
            "id": "evt_test_789",
            "type": "invoice.paid",
            "data": {
                "object": {
                    "id": "inv_stripe_789",
                    "amount_due": 50000,
                    "metadata": {"invoice_id": str(invoice.id)},
                    "status": "paid"
                }
            }
        }
        
        with patch("finances.views.stripe.Webhook.construct_event", return_value=webhook_data), \
             patch("finances.views.settings.STRIPE_WEBHOOK_SECRET", "test_secret"):
            response = self.client.post(
                self.stripe_webhook_url,
                data=json.dumps(webhook_data),
                content_type='application/json',
                HTTP_STRIPE_SIGNATURE='test_sig'
            )
            self.assertEqual(response.status_code, 200)
        
        # Step 3: After payment invoice should not be current anymore
        response_after = self.client.get(self.invoices_url)
        
        # Current invoice should be None (no pending invoices)
        current_invoice_after = response_after.context.get('current_invoice')
        self.assertIsNone(current_invoice_after)
        
        # No Pay Now button
        self.assertNotContains(response_after, "Pay Now")
        
        # Invoice should appear in past invoices with Paid status
        self.assertContains(response_after, "Status: Paid")
        self.assertContains(response_after, "$500.00")
    
    # Test the entire flow
    @patch("finances.views.stripe")
    def test_complete_payment_flow(self, mock_stripe):
        
        # Step 1: Create pending invoice
        invoice = self.create_invoice(
            user=self.client_user,
            status="PENDING",
            amount=75000,
            paid=False
        )
        
        # Step 2: Client views invoice page
        response_view = self.client.get(self.invoices_url)
        self.assertEqual(response_view.status_code, 200)
        current = response_view.context.get('current_invoice')
        self.assertEqual(current.amount, 75000)
        
        # Step 3: Client clicks Pay Now, gets redirected to Stripe
        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/session_complete"
        mock_stripe.checkout.Session.create.return_value = mock_session
        
        checkout_url = reverse(self.checkout_url_name, args=[invoice.id])
        response_checkout = self.client.get(checkout_url)
        self.assertEqual(response_checkout.status_code, 302)
        
        # Step 4: Stripe sends webhook for successful payment
        webhook_data = {
            "id": "evt_complete_flow",
            "type": "invoice.paid",
            "data": {
                "object": {
                    "id": "inv_complete",
                    "amount_due": 75000,
                    "metadata": {"invoice_id": str(invoice.id)},
                    "status": "paid"
                }
            }
        }
        
        with patch("finances.views.stripe.Webhook.construct_event", return_value=webhook_data), \
             patch("finances.views.settings.STRIPE_WEBHOOK_SECRET", "test_secret"):
            response_webhook = self.client.post(
                self.stripe_webhook_url,
                data=json.dumps(webhook_data),
                content_type='application/json',
                HTTP_STRIPE_SIGNATURE='test_sig'
            )
            self.assertEqual(response_webhook.status_code, 200)
        
        # Step 5: Verify database was updated
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "PAID")
        self.assertTrue(invoice.paid)
        
        # Step 6: Verify payment record created
        payment = Payment.objects.filter(user=self.client_user).first()
        self.assertIsNotNone(payment)
        self.assertEqual(payment.status, "SUCCESS")
        
        # Step 7: Client views updated invoice page
        response_final = self.client.get(self.invoices_url)
        
        # No current pending invoice
        current_final = response_final.context.get('current_invoice')
        self.assertIsNone(current_final)
        
        # Invoice in past invoices with Paid status
        self.assertContains(response_final, "Status: Paid")
        self.assertContains(response_final, "$750.00")