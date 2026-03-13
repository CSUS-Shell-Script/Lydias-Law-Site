from datetime import timedelta

from django.urls import reverse
from django.utils import timezone 
from django.contrib.messages import get_messages
from django.contrib.auth import get_user_model, authenticate
from django.contrib.sites.models import Site
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, MagicMock

from allauth.socialaccount.models import SocialApp

from finances.models import Invoice
from users.models import AdminProfile
from decimal import Decimal

import logging

import json

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
