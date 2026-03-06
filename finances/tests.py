from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from finances.models import Invoice
from users.models import User


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
