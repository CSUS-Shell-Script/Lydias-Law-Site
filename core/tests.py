from datetime import timedelta
from datetime import timedelta

from django.contrib.messages import get_messages
from django.test import TestCase, Client, RequestFactory
from django.urls import reverse
from django.utils import timezone
from django.utils import timezone

from sitecontent.models import WebsiteContent
from appointments.models import Appointments, Invitee
from sitecontent.models import FAQItem, WebsiteContent
from users.models import User
from django.contrib.auth import get_user_model
from finances.models import Invoice
from allauth.account.models import EmailAddress
from django.core.exceptions import PermissionDenied
from django.template import Context, Template
from core.decorators import superuser_required

User = get_user_model()

############################### Public pages ###############################

# Public page tests (LLW-276)
class PublicPagesTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):

        # Create website content (temporary databse)
        WebsiteContent.objects.create(

            # Home page temporary database for test
            frontPageHeader = "Home page heading",
            frontPageDescription = "Mission Statement",

            # Practice page temporary database for test
            stepParentAdoptionDescription="Step-parent adoption description",
            adultAdoptionDescription="Adult adoption description",
            guardianshipDescription="Guardianship description",
            guardianshipToAdoptionDescription="Guardianship to adoption description",
            independentAdoptionDescription="Independent adoption description",
        )

    # Django made client account
    def setUp(self):
        self.client = Client()   

    ############################### Home page ###############################

    # Test: Home page returns 200
    def test_home_page_returns_200(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)

    # Test: Home page uses correct template
    def test_home_page_uses_correct_template(self):
        response = self.client.get(reverse('home'))
        self.assertTemplateUsed(response, 'home.html')

    # Test: Home page contains header text
    def test_home_page_heading_text(self):
        response = self.client.get(reverse('home'))
        self.assertTemplateUsed(response, 'home.html')

    # Test: Home page contains mission statement
    def test_home_page_contains_mission_statement(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'Home page heading')

    ############################### About page ###############################

    # Test: About page returns 200
    def test_about_page_returns_200(self):
        response = self.client.get(reverse('about'))
        self.assertEqual(response.status_code, 200)

    # Test: About page conatins biography
    def test_about_page_contains_biography_section(self):
        response = self.client.get(reverse('about'))
        self.assertContains(response, 'About Lydia A. Suprun')
    
    ############################### Practice Areas page ###############################

    # Test: Practice Areas page returns 200
    def test_practice_areas_page_returns_200(self):
        response = self.client.get(reverse('practice_areas'))
        self.assertEqual(response.status_code, 200)

   # Test: Practice Areas page contains all 5 practice areas :
    # (Step-Parent, Adult, Guardianship, Guardianship-to-Adoption, Independent)
    def test_practice_areas_page_contains_all_practice_areas(self):
        response = self.client.get(reverse('practice_areas'))
        self.assertContains(response, 'Step-Parent Adoption')
        self.assertContains(response, 'Adult Adoption')
        self.assertContains(response, 'Guardianship')
        self.assertContains(response, 'Guardianship to Adoption')
        self.assertContains(response, 'Independent Adoption')
    
    ############################### Contact page ###############################

    # Test: Contact page returns 200
    def test_contact_page_returns_200(self):
        response = self.client.get(reverse('contact'))
        self.assertEqual(response.status_code, 200)

    ############################### Payment page ###############################

    # Test: Payment (invoice lookup) page returns 200
    def test_payment_page_returns_200(self):
        response = self.client.get(reverse('payment'))
        self.assertEqual(response.status_code, 200)

    # Test: Payment page POST requires invoice ID
    def test_payment_page_post_requires_invoice_id(self):
        response = self.client.post(reverse('payment'), {})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Incorrect Invoice ID.", response.content.decode())

    # Test: Payment page POST with invalid invoice ID (non-digit) shows error
    def test_payment_page_post_invalid_invoice_id_non_digit(self):
        response = self.client.post(reverse('payment'), {'invoice_id': 'abc'})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Incorrect Invoice ID.", response.content.decode())

    # Test: Payment page POST with invalid invoice ID (not exists) shows error
    def test_payment_page_post_invalid_invoice_id_not_exists(self):
        response = self.client.post(reverse('payment'), {'invoice_id': '99999'})
        self.assertEqual(response.status_code, 404)
        self.assertIn("Incorrect Invoice ID.", response.content.decode())

    # Test: Payment page POST with valid invoice ID redirects to checkout
    def test_payment_page_post_valid_invoice_id_redirects(self):
        user = User.objects.create_user(email='test@example.com', password='pass')
        invoice = Invoice.objects.create(user=user, amount=1000)
        response = self.client.post(reverse('payment'), {'invoice_id': str(invoice.id)})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('create_checkout_session', args=[invoice.id]))

    # Test: Payment page POST with already-paid invoice shows appropriate error
    def test_payment_page_post_paid_invoice_shows_error(self):
        user = User.objects.create_user(email='paid@example.com', password='pass')
        invoice = Invoice.objects.create(user=user, amount=1000, status=Invoice.Status.PAID, paid=True)
        response = self.client.post(reverse('payment'), {'invoice_id': str(invoice.id)}, follow=True)
        self.assertRedirects(response, reverse('payment'))
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "This invoice has already been paid. Thank You!")
        self.assertEqual(messages[0].level, 30)

    # Payment Success page #

    # Test: Payment success page renders with order summary
    def test_payment_success_page_renders_with_order_summary(self):
        response = self.client.get(reverse('payment_success'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Order Summary')

    # Test: Payment success shows "Payment Confirmed" message
    def test_payment_success_shows_payment_confirmed_message(self):
        response = self.client.get(reverse('payment_success'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Payment Confirmed!')

    # Test: Payment success contains close/return button
    def test_payment_success_contains_close_button(self):
        response = self.client.get(reverse('payment_success'))
        self.assertEqual(response.status_code, 200)
        # Check for essential button attributes rather than exact HTML structure.
        self.assertContains(response, 'href="/"')
        self.assertContains(response, '>Close</a>')
        self.assertContains(response, 'btn')

    # Payment Failure page #

    # Test: Transaction failure page renders
    def test_transaction_failure_page_renders(self):
        response = self.client.get(reverse('payment_failure'))
        self.assertEqual(response.status_code, 200)

    # Test: Retry button present on failure page
    def test_retry_button_present_on_failure_page(self):
        response = self.client.get(reverse('payment_failure'))
        self.assertEqual(response.status_code, 200)
        # Check for essential button attributes rather than exact HTML structure.
        self.assertContains(response, 'href="/payment/"')
        self.assertContains(response, '>Retry Payment</a>')
        self.assertContains(response, 'btn')

    ############################### Privacy page ###############################

    # Test: Privacy page returns 200
    def test_privacy_page_returns_200(self):
        response = self.client.get(reverse('privacy'))
        self.assertEqual(response.status_code, 200)

############################# Navigation Bar #############################
# Test For Public Nav Bar - 277
class PublicNavbarTests(TestCase):
    def test_public_nav_contains_expected_links(self):
       # Access public page -> home
        response = self.client.get(reverse('home'))

        # Nav Contains logo linking to home page
        self.assertContains(response, 'href="/"')

        # Nav contains links to diff pages -> about, payment, contact, login ...
        self.assertContains(response, 'Practice Areas')
        self.assertContains(response, 'About')
        self.assertContains(response, 'Contact')
        self.assertContains(response, 'Privacy Policy')
        self.assertContains(response, 'Payment')
        self.assertContains(response, 'Login')
        
        # Nav does NOT show dashboard, logout, transaction history
        self.assertNotContains(response, 'Dashboard')
        self.assertNotContains(response, 'Logout')
        self.assertNotContains(response, 'Transaction History') 

############################### Client pages ###############################

# Client Dashbaord test (LLW-279)
class ClientDashboardTests(TestCase):
    def setUp(self):

        # Make client user
        self.user = User.objects.create_user(
            email="client@example.com",
            password="pass",
            first_name="Jane",
            last_name="Doe",
            phone_number="5551234567",
            is_active=True,
        )

        # Create invoice object for client user (for 'Amount Due' on dashboard)
        self.invoice = Invoice.objects.create(
            user=self.user,
            amount=12300,
        )

        # Create appointments for client user
        now = timezone.now()
        self.appt1 = Appointments.objects.create(
            user_id=self.user,
            start_time=now + timedelta(days=1),
            comments="Appointment 1",
            approved=True,
        )
        self.appt2 = Appointments.objects.create(
            user_id=self.user,
            start_time=now + timedelta(days=2),
            comments="Appointment 2",
            approved=True,
        )
        self.appt3 = Appointments.objects.create(
            user_id=self.user,
            start_time=now + timedelta(days=3),
            comments="Appointment 3",
            approved=True,
        )
        self.appt4 = Appointments.objects.create(
            user_id=self.user,
            start_time=now + timedelta(days=4),
            comments="Appointment 4",
            approved=True,
        )

    # Test: Dashboard requires login (redirects if not authenticated)
    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("client_dashboard"))
        self.assertEqual(response.status_code, 302)

    # Test: Dashboard returns 200 for authenticated client
    def test_dashboard_returns_200_for_authenticated_client(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("client_dashboard"))
        self.assertEqual(response.status_code, 200)

    # Test: Dashboard context includes upcoming appointments (next 3)
    def test_dashboard_context_includes_next_3_upcoming_appointments(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("client_dashboard"))

        self.assertIn("upcoming_appts", response.context)
        upcoming = response.context["upcoming_appts"]
        self.assertEqual(len(upcoming), 3)

    # Test: Dashboard shows amount due / retainer balance
    def test_dashboard_shows_amount_due(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("client_dashboard"))
        self.assertContains(response, "Amount Due:")
        self.assertContains(response, "$123")

    # Test: Dashboard contains link to payment page
    def test_dashboard_contains_link_to_payment_page(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("client_dashboard"))
        self.assertContains(response, reverse("client_invoices"))


# LLW-248 / LLW-251 — Client account page (backend + validation) testing
class ClientAccountViewTests(TestCase):
    """
    LLW-248: Backend logic — GET populates from DB, POST persists changes.
    LLW-251: Validation rules that match client-side constraints (blank names,
             digits-only phone) are enforced server-side as well.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="client@example.com",
            password="testpass123",
            first_name="Jane",
            last_name="Doe",
            phone_number="5551234567",
            is_active=True,
        )
        self.url = reverse("client_account")

    def _messages(self, response):
        return [m.message for m in get_messages(response.wsgi_request)]

    # auth guard
    def test_unauthenticated_redirects_to_login(self):
        resp = self.client.get(self.url)
        self.assertNotEqual(resp.status_code, 200)
        self.assertIn(resp.status_code, (302, 301))

    # GET pulls from DB properly
    def test_get_populates_first_name(self):
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Jane")

    def test_get_populates_last_name(self):
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertContains(resp, "Doe")

    def test_get_populates_email(self):
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertContains(resp, "client@example.com")

    def test_get_formats_10_digit_phone(self):
        """10-digit phone number should be formatted as (XXX) XXX-XXXX."""
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertContains(resp, "(555) 123-4567")

    def test_get_non_10_digit_phone_falls_back_to_raw(self):
        self.user.phone_number = "123456"
        self.user.save(update_fields=["phone_number"])
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertContains(resp, "123456")

    # POST name succeeds
    def test_post_name_updates_first_and_last_name_in_db(self):
        self.client.force_login(self.user)
        self.client.post(self.url, {"field": "name", "first_name": "Alice", "last_name": "Smith"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Alice")
        self.assertEqual(self.user.last_name, "Smith")

    def test_post_name_success_shows_success_message(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            self.url, {"field": "name", "first_name": "Alice", "last_name": "Smith"}, follow=True
        )
        self.assertIn("Name updated successfully.", self._messages(resp))

    def test_post_name_redirects_after_success(self):
        self.client.force_login(self.user)
        resp = self.client.post(self.url, {"field": "name", "first_name": "Alice", "last_name": "Smith"})
        self.assertRedirects(resp, self.url)

    # POST name blank is valid
    def test_post_name_blank_first_name_rejected(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            self.url, {"field": "name", "first_name": "", "last_name": "Smith"}, follow=True
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Jane")  # unchanged
        self.assertIn("First name and last name cannot be blank.", self._messages(resp))

    def test_post_name_blank_last_name_rejected(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            self.url, {"field": "name", "first_name": "Alice", "last_name": ""}, follow=True
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.last_name, "Doe")  # unchanged
        self.assertIn("First name and last name cannot be blank.", self._messages(resp))

    def test_post_name_whitespace_only_rejected(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            self.url, {"field": "name", "first_name": "   ", "last_name": "   "}, follow=True
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Jane")
        self.assertIn("First name and last name cannot be blank.", self._messages(resp))

    # POST phone succeeds
    def test_post_phone_updates_phone_in_db(self):
        self.client.force_login(self.user)
        self.client.post(self.url, {"field": "phone", "new_value": "8005551234"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, "8005551234")

    def test_post_phone_success_shows_success_message(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            self.url, {"field": "phone", "new_value": "8005551234"}, follow=True
        )
        self.assertIn("Phone number updated successfully.", self._messages(resp))

    def test_post_phone_redirects_after_success(self):
        self.client.force_login(self.user)
        resp = self.client.post(self.url, {"field": "phone", "new_value": "8005551234"})
        self.assertRedirects(resp, self.url)

    # POST phone is digit-only
    def test_post_phone_blank_rejected(self):
        self.client.force_login(self.user)
        resp = self.client.post(self.url, {"field": "phone", "new_value": ""}, follow=True)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, "5551234567")  # unchanged
        self.assertIn("Phone number cannot be blank.", self._messages(resp))

    def test_post_phone_with_letters_rejected(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            self.url, {"field": "phone", "new_value": "555-123-4567"}, follow=True
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, "5551234567")
        self.assertIn("Phone number must be 7-15 digits (numbers only).", self._messages(resp))

    def test_post_phone_too_short_rejected(self):
        self.client.force_login(self.user)
        resp = self.client.post(self.url, {"field": "phone", "new_value": "123"}, follow=True)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, "5551234567")
        self.assertIn("Phone number must be 7-15 digits (numbers only).", self._messages(resp))

    def test_post_phone_too_long_rejected(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            self.url, {"field": "phone", "new_value": "1234567890123456"}, follow=True
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, "5551234567")
        self.assertIn("Phone number must be 7-15 digits (numbers only).", self._messages(resp))

    # email is read-only (subject to change, discussing with team later)
    def test_post_email_field_is_rejected(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            self.url, {"field": "email", "new_value": "newemail@example.com"}, follow=True
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "client@example.com")  # unchanged
        self.assertIn("That field cannot be updated here.", self._messages(resp))

    # unknown field cannot be updated
    def test_post_unknown_field_shows_error(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            self.url, {"field": "retainer_balance", "new_value": "9999"}, follow=True
        )
        self.assertIn("That field cannot be updated here.", self._messages(resp))

# CLIENT NAVIGATION BAR TEST - LLW 278
class ClientNavbarTest(TestCase):
    def setUp(self):
        self.client = Client()

        WebsiteContent.objects.create(
            frontPageHeader="Test Header",
            frontPageDescription="Test Description",
        )

        # Create Test Client 
        self.user = User.objects.create_user(
            email="clientUser@test.com",
            password="Pass123!",   
            role=User.Role.CLIENT, 
            is_active=True,                   
        )

        EmailAddress.objects.create(
            user=self.user,
            email=self.user.email,
            primary=True,
            verified=True,
        )


    def test_navbar_for_logged_in_client(self):
        # Log in the user        
        self.client.force_login(self.user)

        response = self.client.get("/client/dashboard/", follow=True)        
        self.assertEqual(response.status_code, 200)

        # Should be visible
        self.assertContains(response, reverse("client_practice_areas"))
        self.assertContains(response, reverse("client_about"))
        self.assertContains(response, reverse("client_contact"))
        self.assertContains(response, reverse("client_privacy"))
        self.assertContains(response, reverse("client_dashboard"))
        self.assertContains(response, reverse("client_invoices"))
        self.assertContains(response, reverse("client_account"))

        self.assertContains(response, "Logout")
        self.assertContains(response, 'method="post"')

        # Should NOT be visible
        self.assertNotContains(response, "/users/login")

    def test_logout_redirects_to_home(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("logout"))

        self.assertRedirects(response, reverse("home"))
        # Confirm user is actually logged out
        response  = self.client.get("/client/dashboard/")
        self.assertNotEqual(response.status_code, 200)

    def test_logo_links_to_home(self):
        self.client.force_login(self.user)

        response = self.client.get("/client/dashboard/", follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{reverse("home")}"')

# LLW-298 - Test: No cross-user data access (client A can't see client B's data)
class DataIsolationTests(TestCase):
    def setUp(self):

        # User1
        self.user1 = User.objects.create_user(
            email="a@test.com",
            password="pass",   
            role=User.Role.CLIENT, 
            is_active=True,                   
        )
        
        # User2
        self.user2 = User.objects.create_user(
            email="b@test.com",
            password="pass",   
            role=User.Role.CLIENT, 
            is_active=True,                   
        )

        # User1 and User2 appointments
        now = timezone.now()
        self.appt1 = Appointments.objects.create(
            user_id=self.user1,
            start_time=now + timedelta(days=1),
            comments="Appointment for user1",
            approved=True,
        )
        self.appt2 = Appointments.objects.create(
            user_id=self.user2,
            start_time=now + timedelta(days=1),
            comments="Appointment for user2",
            approved=True,
        )

    # Check and make sure they have the proper text for their user appointment
    def test_user_cannot_see_other_users_data(self):
        self.client.login(email="a@test.com", password="pass")

        response = self.client.get(reverse("client_dashboard"))

        self.assertContains(response, "Appointment for user1")
        self.assertNotContains(response, "Appointment for user2")

# LLW-298 - Test: Every /client/* route returns 302 (redirect to login) for unauthenticated users
class ClientRouteAuthTests(TestCase):
    def test_client_routes_require_login(self):
        urls = [
            reverse("client_about"),
            reverse("client_account"),
            reverse("client_contact"),
            reverse("client_dashboard"),
            reverse("client_practice_areas"),
            reverse("client_invoices"),
            reverse("client_privacy"),
            reverse("client_appointment_confirmation"),
        ]

        for url in urls:
            response = self.client.get(url)
            print(f"{url} -> {response.status_code}")
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login", response.url)

# LLW-298 - Test: Webhook endpoints (/webhooks/stripe/, /appointments/webhooks/calendly/) are CSRF exempt
# Also checking if these paths exists
class WebhookTests(TestCase):
    def test_stripe_webhook_csrf_exempt(self):
        response = self.client.post("/webhooks/stripe/", data={})
        self.assertNotEqual(response.status_code, 403)
        self.assertNotEqual(response.status_code, 404) # make sure this path exists

    def test_calendly_webhook_csrf_exempt(self):
        response = self.client.post("/appointments/webhooks/calendly/", data={})
        self.assertNotEqual(response.status_code, 403)
        self.assertNotEqual(response.status_code, 404) # make sure this path exists

############################### Admin pages ###############################

# LLW-298 - Test: Every /administrator/* route returns 403 for non-superusers
class AdminPermissionTests(TestCase):

    def setUp(self):
        # Make client user
        self.client_user = User.objects.create_user(
            email="client@example.com",
            password="pw",
            first_name="Client",
            last_name="User",
            is_staff=False,
            is_active=True,
        )

        # Give client user an appointment to test
        now = timezone.now()
        self.appointment = Appointments.objects.create(
            user_id=self.client_user,
            start_time=now + timedelta(days=1),
            comments="Appointment 1",
            approved=True,
        )

    # Test if /administrator/* route returns 403 for non-superusers
    def test_admin_routes_forbidden_for_non_superuser(self):
        self.client.force_login(self.client_user)
        urls = [
            reverse("admin_dashboard"),
            reverse("admin_transactions"),
            reverse("admin_clients"),
            reverse("admin_schedule"),
            reverse("admin_editor"),
            reverse("admin_history"),
            reverse("admin_appointments"),
            reverse("admin_create_invoices"),
            reverse("admin_invoice_confirmation"),
            reverse("admin_appointment_detail", kwargs={"pk": self.appointment.pk}),
        ]

        for url in urls:
            response = self.client.get(url)
            print(f"{url} -> {response.status_code}")
            self.assertEqual(response.status_code, 403)

    # Test /administrator/* route returns 403 for non-superusers but for POST links
    def test_admin_post_routes_forbidden_for_non_superuser(self):
        self.client.force_login(self.client_user)

        urls = [
            reverse("admin_appointment_cancel", kwargs={"pk": self.appointment.pk}),
            reverse("admin_appointment_accept", kwargs={"pk": self.appointment.pk}),
            reverse("admin_appointment_update_status", kwargs={"pk": self.appointment.pk}),
        ]

        for url in urls:
            response = self.client.post(url)
            print(f"{url} -> {response.status_code}")
            self.assertEqual(response.status_code, 403)

class AdminAppointmentActionsTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            email="admin@example.com",
            password="pw",
            first_name="Admin",
            last_name="User",
            is_staff=True,
            is_active=True,
        )
        self.client_user = User.objects.create_user(
            email="client@example.com",
            password="pw",
            first_name="Client",
            last_name="User",
            is_staff=False,
            is_active=True,
        )

        self.appt_pending = Appointments.objects.create(
            user_id=self.client_user,
            start_time=timezone.now() + timedelta(days=1),
            status=Appointments.Status.PENDING,
        )
        self.invitee = Invitee.objects.create(
            appointment=self.appt_pending,
            name="Test Invitee",
            email="invitee@example.com",
            phone_number="5551112222",
        )

    def _messages(self, response):
        return [m.message for m in get_messages(response.wsgi_request)]

    def test_cancel_requires_staff(self):
        non_staff = User.objects.create_user(
            email="nonstaff@example.com",
            password="pw",
            first_name="Non",
            last_name="Staff",
            is_staff=False,
            is_active=True,
        )
        self.client.force_login(non_staff)
        url = reverse("admin_appointment_cancel", args=[self.appt_pending.pk])
        resp = self.client.post(url, data={"reason": "No longer needed"})
        self.assertEqual(resp.status_code, 403)

    def test_cancel_requires_reason(self):
        self.client.force_login(self.admin_user)
        url = reverse("admin_appointment_cancel", args=[self.appt_pending.pk])
        resp = self.client.post(url, data={"reason": ""}, follow=True)

        self.appt_pending.refresh_from_db()
        self.assertEqual(self.appt_pending.status, Appointments.Status.PENDING)
        self.assertIn("Cancellation reason is required.", self._messages(resp))

    def test_cancel_requires_pending_or_confirmed(self):
        appt = Appointments.objects.create(
            user_id=self.client_user,
            start_time=timezone.now() + timedelta(days=2),
            status=Appointments.Status.COMPLETED,
        )
        self.client.force_login(self.admin_user)
        url = reverse("admin_appointment_cancel", args=[appt.pk])
        resp = self.client.post(url, data={"reason": "Test"}, follow=True)

        appt.refresh_from_db()
        self.assertEqual(appt.status, Appointments.Status.COMPLETED)
        self.assertIn("Only Pending or Confirmed appointments can be cancelled.", self._messages(resp))

    def test_cancel_success_updates_appointment_and_invitees(self):
        self.client.force_login(self.admin_user)
        url = reverse("admin_appointment_cancel", args=[self.appt_pending.pk])
        resp = self.client.post(url, data={"reason": "Client requested"}, follow=True)

        self.appt_pending.refresh_from_db()
        self.invitee.refresh_from_db()

        self.assertEqual(self.appt_pending.status, Appointments.Status.CANCELLED)
        self.assertEqual(self.appt_pending.cancellation_reason, "Client requested")
        self.assertIsNotNone(self.appt_pending.cancelled_at)
        self.assertTrue(self.invitee.canceled)
        self.assertEqual(self.invitee.cancellation_reason, "Client requested")
        self.assertIn("Appointment cancelled.", self._messages(resp))

    def test_cancel_with_calendly_uri_adds_expected_skip_message(self):
        self.appt_pending.calendly_event_uri = "https://api.calendly.com/scheduled_events/TEST"
        self.appt_pending.save(update_fields=["calendly_event_uri"])

        self.client.force_login(self.admin_user)
        url = reverse("admin_appointment_cancel", args=[self.appt_pending.pk])
        resp = self.client.post(url, data={"reason": "Client requested"}, follow=True)

        self.appt_pending.refresh_from_db()
        self.assertEqual(self.appt_pending.status, Appointments.Status.CANCELLED)
        self.assertIn("Calendly cancellation skipped (site not live yet — expected).", self._messages(resp))

    def test_status_update_blocks_invalid_transition(self):
        self.client.force_login(self.admin_user)
        url = reverse("admin_appointment_update_status", args=[self.appt_pending.pk])
        resp = self.client.post(url, data={"status": Appointments.Status.COMPLETED}, follow=True)

        self.appt_pending.refresh_from_db()
        self.assertEqual(self.appt_pending.status, Appointments.Status.PENDING)
        self.assertIn("That status change isn’t allowed.", self._messages(resp))

    def test_status_update_allows_pending_to_confirmed(self):
        self.client.force_login(self.admin_user)
        url = reverse("admin_appointment_update_status", args=[self.appt_pending.pk])
        resp = self.client.post(url, data={"status": Appointments.Status.CONFIRMED}, follow=True)

        self.appt_pending.refresh_from_db()
        self.assertEqual(self.appt_pending.status, Appointments.Status.CONFIRMED)
        self.assertIn("Status updated.", self._messages(resp))

    def test_status_update_cancel_requires_reason(self):
        self.client.force_login(self.admin_user)
        url = reverse("admin_appointment_update_status", args=[self.appt_pending.pk])
        resp = self.client.post(url, data={"status": Appointments.Status.CANCELLED, "reason": ""}, follow=True)

        self.appt_pending.refresh_from_db()
        self.assertEqual(self.appt_pending.status, Appointments.Status.PENDING)
        self.assertIn("Cancellation reason is required.", self._messages(resp))

    def test_status_update_cancel_success(self):
        self.client.force_login(self.admin_user)
        url = reverse("admin_appointment_update_status", args=[self.appt_pending.pk])
        resp = self.client.post(
            url,
            data={"status": Appointments.Status.CANCELLED, "reason": "No longer needed"},
            follow=True,
        )

        self.appt_pending.refresh_from_db()
        self.invitee.refresh_from_db()

        self.assertEqual(self.appt_pending.status, Appointments.Status.CANCELLED)
        self.assertEqual(self.appt_pending.cancellation_reason, "No longer needed")
        self.assertIsNotNone(self.appt_pending.cancelled_at)
        self.assertTrue(self.invitee.canceled)
        self.assertEqual(self.invitee.cancellation_reason, "No longer needed")
        self.assertIn("Status updated to Cancelled.", self._messages(resp))

    def test_status_update_terminal_state_is_blocked(self):
        appt = Appointments.objects.create(
            user_id=self.client_user,
            start_time=timezone.now() + timedelta(days=3),
            status=Appointments.Status.CANCELLED,
            cancellation_reason="Already cancelled",
            cancelled_at=timezone.now(),
        )
        self.client.force_login(self.admin_user)
        url = reverse("admin_appointment_update_status", args=[appt.pk])
        resp = self.client.post(url, data={"status": Appointments.Status.CONFIRMED}, follow=True)

        appt.refresh_from_db()
        self.assertEqual(appt.status, Appointments.Status.CANCELLED)
        self.assertIn("That status change isn’t allowed.", self._messages(resp))

#Test cases for the admin_clients view
class AdminClientsViewTest(TestCase):    
    def setUp(self):
        # Create admin for login 
        self.admin = User.objects.create_user(
            email='admin@example.com',
            password='adminpass',  # create_user hashes this automatically
            first_name='Admin',
            last_name='User',
            role=User.Role.ADMIN,
            is_active=True  # Make sure user is active
        )
        
        # Create test clients
        self.client_with_balance = User.objects.create_user(
            email='client1@example.com',
            password='password123',
            first_name='John',
            last_name='Doe',
            phone_number='123-456-7890',
            role=User.Role.CLIENT,
            retainer_balance=100,
            is_active=True
        )
        
        self.client_no_balance = User.objects.create_user(
            email='client2@example.com',
            password='password123',
            first_name='Jane',
            last_name='Smith',
            phone_number='987-654-3210',
            role=User.Role.CLIENT,
            retainer_balance=0,
            is_active=True
        )
        
        # Create non-client users that should NOT appear
        self.guest = User.objects.create_user(
            email='guest@example.com',
            password='password123',
            first_name='Guest',
            last_name='User',
            role=User.Role.GUEST,
            is_active=True
        )
        
    #Test that only CLIENT role users appear
    def test_only_clients_shown(self):
        # Login first
        login_successful = self.client.login(email='admin@example.com', password='adminpass')
        self.assertTrue(login_successful, "Admin login failed!")
        
        # Make the request
        response = self.client.get(reverse('admin_clients'))
        
        # Check response
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context)
        
        # Should only show 2 clients (John and Jane)
        self.assertEqual(len(response.context['page_obj']), 2)
        
        # Verify all returned users have CLIENT role
        for user in response.context['page_obj']:
            self.assertEqual(user.role, User.Role.CLIENT)
            
        # Verify guest is NOT in the results
        user_emails = [user.email for user in response.context['page_obj']]
        self.assertNotIn('guest@example.com', user_emails)

    #Test search functionality      
    def test_search_works(self):
        self.client.login(email='admin@example.com', password='adminpass')
        
        # Search by first name
        response = self.client.get(reverse('admin_clients'), {'search': 'John'})
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context)
        self.assertEqual(len(response.context['page_obj']), 1)
        self.assertEqual(response.context['page_obj'][0].email, 'client1@example.com')
        
        # Search by email
        response = self.client.get(reverse('admin_clients'), {'search': 'client2'})
        self.assertEqual(len(response.context['page_obj']), 1)
        self.assertEqual(response.context['page_obj'][0].email, 'client2@example.com')
        
        # Search by phone
        response = self.client.get(reverse('admin_clients'), {'search': '123-456'})
        self.assertEqual(len(response.context['page_obj']), 1)
        self.assertEqual(response.context['page_obj'][0].email, 'client1@example.com')
        
    #Test balance filter functionality
    def test_balance_filter_works(self):
        self.client.login(email='admin@example.com', password='adminpass')
        
        # Filter has balance
        response = self.client.get(reverse('admin_clients'), {'balance': 'has_balance'})
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context)
        self.assertEqual(len(response.context['page_obj']), 1)
        self.assertEqual(response.context['page_obj'][0].retainer_balance, 100)
        
        # Filter no balance
        response = self.client.get(reverse('admin_clients'), {'balance': 'no_balance'})
        self.assertEqual(len(response.context['page_obj']), 1)
        self.assertEqual(response.context['page_obj'][0].retainer_balance, 0)
        
    #Test search + balance filter together
    def test_combined_filters(self):
        self.client.login(email='admin@example.com', password='adminpass')
        
        response = self.client.get(reverse('admin_clients'), {
            'search': 'John',
            'balance': 'has_balance'
        })
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context)
        self.assertEqual(len(response.context['page_obj']), 1)
        self.assertEqual(response.context['page_obj'][0].first_name, 'John')
        self.assertEqual(response.context['page_obj'][0].retainer_balance, 100)

class AdminAppointmentHistoryTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(
        email="admin@test.com",
        password="pass123",
        role=User.Role.ADMIN,   
        is_superuser=True,     
        is_staff=True           
        )

        self.client.force_login(self.admin)

        self.client.login(username="admin", password="pass123")

        self.url = reverse("admin_appointments")

        self.now = timezone.now()

        # past appointments
        self.appt1 = Appointments.objects.create(
            user_id=self.admin,
            start_time=self.now - timedelta(days=1),
            status=Appointments.Status.COMPLETED,
            comments="Past 1"
        )

        self.appt2 = Appointments.objects.create(
            user_id=self.admin,
            start_time=self.now - timedelta(days=2),
            status=Appointments.Status.CANCELLED,
            comments="Past 2"
        )

        Invitee.objects.create(
            appointment=self.appt1,
            name="John Doe",
            email="john@test.com",
            phone_number="123"
        )

    # 1. Lists past appointments
    def test_lists_past_appointments(self):
        response = self.client.get(self.url)

        self.assertContains(response, "Past 1")
        self.assertContains(response, "Past 2")

    # 2. Each appointment shows comments section
    def test_comments_are_displayed(self):
        response = self.client.get(self.url)

        self.assertContains(response, "Past 1")
        self.assertContains(response, "Past 2")

    # 3. Page loads (basic sanity for history page)
    def test_history_page_loads(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

    # 4. Appointment info is shown (name + basic fields)
    def test_appointment_shows_basic_info(self):
        response = self.client.get(self.url)

        self.assertContains(response, "John Doe")
############################### Admin Editor Page (LLW-289) ###############################

class AdminEditorTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.content = WebsiteContent.objects.create(
            frontPageHeader="Test Header",
            frontPageDescription="<p>Test description</p>",
            nameTitle="Lydia A. Suprun",
            aboutMeDescription="<p>About text</p>",
            officeLocation="123 Main St",
            stepParentAdoptionDescription="<p>Step-parent</p>",
            adultAdoptionDescription="<p>Adult</p>",
            guardianshipDescription="<p>Guardianship</p>",
            guardianshipToAdoptionDescription="<p>G to A</p>",
            independentAdoptionDescription="<p>Independent</p>",
            footerDescription="<p>Footer</p>",
        )

    def setUp(self):
        self.superuser = User.objects.create_user(
            email="admin@editor.com",
            password="pw",
            first_name="Admin",
            last_name="Editor",
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )
        self.regular_user = User.objects.create_user(
            email="regular@example.com",
            password="pw",
            first_name="Regular",
            last_name="User",
            is_active=True,
        )

    # commented out for now bc we aren't enforcing superuser for admin dashboard yet
    # Test: Editor page requires superuser
    # def test_editor_requires_superuser(self):
    #     self.client.force_login(self.regular_user)
    #     response = self.client.get(reverse('admin_editor'))
    #     self.assertNotEqual(response.status_code, 200)

    # Test: GET loads current content into form fields
    def test_get_loads_content_into_form(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('admin_editor'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'admin/editor.html')
        form = response.context['form']
        self.assertEqual(form.initial['frontPageHeader'], "Test Header")
        self.assertEqual(form.initial['nameTitle'], "Lydia A. Suprun")
        self.assertEqual(form.initial['officeLocation'], "123 Main St")

    # Test: GET populates all section fields (home, about, practice areas, contact, FAQ, footer)
    def test_get_populates_all_sections(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('admin_editor'))
        form = response.context['form']
        self.assertEqual(form.initial['frontPageHeader'], "Test Header")
        self.assertEqual(form.initial['frontPageDescription'], "<p>Test description</p>")
        self.assertEqual(form.initial['nameTitle'], "Lydia A. Suprun")
        self.assertEqual(form.initial['aboutMeDescription'], "<p>About text</p>")
        self.assertEqual(form.initial['officeLocation'], "123 Main St")
        self.assertEqual(form.initial['stepParentAdoptionDescription'], "<p>Step-parent</p>")
        self.assertEqual(form.initial['adultAdoptionDescription'], "<p>Adult</p>")
        self.assertEqual(form.initial['guardianshipDescription'], "<p>Guardianship</p>")
        self.assertEqual(form.initial['guardianshipToAdoptionDescription'], "<p>G to A</p>")
        self.assertEqual(form.initial['independentAdoptionDescription'], "<p>Independent</p>")
        self.assertEqual(form.initial['footerDescription'], "<p>Footer</p>")

    # Test: POST updates content and creates new version
    def test_post_updates_content(self):
        self.client.force_login(self.superuser)
        post_data = {
            'frontPageHeader': 'Updated Header',
            'frontPageDescription': '<p>Updated description</p>',
            'nameTitle': 'Updated Name',
            'aboutMeDescription': '<p>Updated about</p>',
            'officeLocation': 'Updated Location',
            'stepParentAdoptionDescription': '<p>Updated step-parent</p>',
            'adultAdoptionDescription': '<p>Updated adult</p>',
            'guardianshipDescription': '<p>Updated guardianship</p>',
            'guardianshipToAdoptionDescription': '<p>Updated g to a</p>',
            'independentAdoptionDescription': '<p>Updated independent</p>',
            'footerDescription': '<p>Updated footer</p>',
        }
        response = self.client.post(reverse('admin_editor'), post_data)
        self.assertRedirects(response, reverse('admin_editor'))

        # Verify the content was saved
        latest = WebsiteContent.objects.order_by('-versionNumber').first()
        self.assertEqual(latest.frontPageHeader, 'Updated Header')
        self.assertEqual(latest.footerDescription, '<p>Updated footer</p>')

    # Test: "Update All" saves all sections in one POST
    def test_update_all_saves_all_sections(self):
        self.client.force_login(self.superuser)
        post_data = {
            'frontPageHeader': 'All Updated Header',
            'frontPageDescription': '<p>All updated desc</p>',
            'nameTitle': 'All Updated Name',
            'aboutMeDescription': '<p>All updated about</p>',
            'officeLocation': 'All Updated Location',
            'stepParentAdoptionDescription': '<p>All updated SP</p>',
            'adultAdoptionDescription': '<p>All updated Adult</p>',
            'guardianshipDescription': '<p>All updated Guard</p>',
            'guardianshipToAdoptionDescription': '<p>All updated GtA</p>',
            'independentAdoptionDescription': '<p>All updated Indep</p>',
            'footerDescription': '<p>All updated footer</p>',
        }
        response = self.client.post(reverse('admin_editor'), post_data)
        self.assertRedirects(response, reverse('admin_editor'))

        latest = WebsiteContent.objects.order_by('-versionNumber').first()
        self.assertEqual(latest.frontPageHeader, 'All Updated Header')
        self.assertEqual(latest.nameTitle, 'All Updated Name')
        self.assertEqual(latest.officeLocation, 'All Updated Location')
        self.assertEqual(latest.stepParentAdoptionDescription, '<p>All updated SP</p>')
        self.assertEqual(latest.adultAdoptionDescription, '<p>All updated Adult</p>')
        self.assertEqual(latest.guardianshipDescription, '<p>All updated Guard</p>')
        self.assertEqual(latest.guardianshipToAdoptionDescription, '<p>All updated GtA</p>')
        self.assertEqual(latest.independentAdoptionDescription, '<p>All updated Indep</p>')
        self.assertEqual(latest.footerDescription, '<p>All updated footer</p>')

    # Test: Success message "Pages Have Been Updated" shown after save
    def test_success_message_shown_after_save(self):
        self.client.force_login(self.superuser)
        post_data = {
            'frontPageHeader': 'Msg Test',
            'frontPageDescription': '',
            'nameTitle': '',
            'aboutMeDescription': '',
            'officeLocation': '',
            'stepParentAdoptionDescription': '',
            'adultAdoptionDescription': '',
            'guardianshipDescription': '',
            'guardianshipToAdoptionDescription': '',
            'independentAdoptionDescription': '',
            'footerDescription': '',
        }
        response = self.client.post(reverse('admin_editor'), post_data, follow=True)
        self.assertEqual(response.status_code, 200)
        msgs = list(get_messages(response.wsgi_request))
        self.assertTrue(any('updated successfully' in str(m) for m in msgs))

############################### Template Pages Tests ###############################
# Template Inheritance and Structure Test - LLW 300 
class TemplateInheritanceTest(TestCase):
    def setUp(self):
        self.client = Client();
        
        self.content = WebsiteContent.objects.create(
            frontPageHeader ="Test Header",
            frontPageDescription="Test Description",
        )

        # 4 FAQ pairs 
        FAQItem.objects.create(question="Question 1", answer="Answer 1", display_order=1, is_active=True)
        FAQItem.objects.create(question="Question 2", answer="Answer 2", display_order=2, is_active=True)
        FAQItem.objects.create(question="Question 3", answer="Answer 3", display_order=3, is_active=True)
        FAQItem.objects.create(question="Question 4", answer="Answer 4", display_order=4, is_active=True)

        # Admin User
        self.admin_user = User.objects.create_user(
            email="admin@test.com",
            password="Pass123!",
            role=User.Role.ADMIN,
            is_active=True,
            is_staff=True,
        )       

        EmailAddress.objects.create(
            user=self.admin_user,
            email=self.admin_user.email,
            primary=True,
            verified=True,
        )

        # Client user
        self.client_user = User.objects.create_user(
            email="client@test.com",
            password="Pass123!",
            role=User.Role.CLIENT,
            is_active=True,
        )
        EmailAddress.objects.create(
            user=self.client_user,
            email=self.client_user.email,
            primary=True,
            verified=True,
        )

    # Public pages extend base.html
    PUBLIC_PAGES = [
        "home",
        "practice_areas",
        "about",
        "contact",
        "privacy",
        "payment",
    ]

    def test_public_pages_use_base_template(self):
        """Public pages extend base.html — verified by presence of public footer."""
        for url_name in self.PUBLIC_PAGES:
            with self.subTest(page=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)
                # Public footer has Practice Areas / About / Contact links
                # pointing to public URLs — unique to footer.html
                self.assertContains(response, reverse("practice_areas"),
                                    msg_prefix=f"Public footer missing on {url_name}")

    # Footer appears on all public pages
    def test_footer_appears_on_all_public_pages(self):
        """footer.html is included on every public page."""
        for url_name in self.PUBLIC_PAGES:
            with self.subTest(page=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)
                # fixed-bottom footer div is unique to all three footer partials
                self.assertContains(response, "fixed-bottom bg-white border-top shadow-sm",
                                    msg_prefix=f"Footer missing on {url_name}")

    # Meta tags / page titles present for SEO
    def test_public_pages_have_meta_charset(self):
        """All public pages should have UTF-8 charset meta tag."""
        for url_name in self.PUBLIC_PAGES:
            with self.subTest(page=url_name):
                response = self.client.get(reverse(url_name))
                self.assertContains(response, 'charset="utf-8"')

    def test_public_pages_have_meta_description(self):
        """All public pages should have a meta description for SEO."""
        for url_name in self.PUBLIC_PAGES:
            with self.subTest(page=url_name):
                response = self.client.get(reverse(url_name))
                self.assertContains(response, 'name="description"',
                                    msg_prefix=f"Meta description missing on {url_name}")

    def test_public_pages_have_viewport_meta(self):
        """All public pages should have a viewport meta tag."""
        for url_name in self.PUBLIC_PAGES:
            with self.subTest(page=url_name):
                response = self.client.get(reverse(url_name))
                self.assertContains(response, 'name="viewport"',
                                    msg_prefix=f"Viewport meta tag missing on {url_name}")

    def test_home_page_has_default_title(self):
        """Home page should have the default SEO title from base.html."""
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Lydia A. Suprun")

    # Admin pages extend base_admin.html
    def test_admin_pages_use_base_admin_template(self):
        """Admin pages extend base_admin.html — verified by presence of admin footer."""
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("admin_dashboard"))
        self.assertEqual(response.status_code, 200)
        # Admin footer uniquely contains these links — not in public or client footer
        self.assertContains(response, reverse("admin_dashboard"))
        self.assertContains(response, reverse("admin_clients"))
        self.assertContains(response, reverse("admin_editor"))

    def test_admin_pages_have_admin_footer(self):
        """Admin footer should appear on admin pages."""
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("admin_dashboard"))
        self.assertContains(response, "fixed-bottom bg-white border-top shadow-sm")
        # Admin footer has Create Invoice — not in any other footer
        self.assertContains(response, "Create Invoice")

    # Client pages extend base_client.html
    def test_client_pages_use_base_client_template(self):
        """Client pages extend base_client.html — verified by presence of client footer."""
        self.client.force_login(self.client_user)
        response = self.client.get(reverse("client_dashboard"), follow=True)
        self.assertEqual(response.status_code, 200)
        # Client footer uniquely contains these links — not in public or admin footer
        self.assertContains(response, reverse("client_dashboard"))
        self.assertContains(response, reverse("client_invoices"))
        self.assertContains(response, reverse("client_account"))

    def test_client_pages_have_client_footer(self):
        """Client footer should appear on all client pages."""
        self.client.force_login(self.client_user)
        CLIENT_PAGES = [
            reverse("client_about"),
            reverse("client_contact"),
            reverse("client_privacy"),
            reverse("client_dashboard"),
        ]
        for url in CLIENT_PAGES:
            with self.subTest(url=url):
                response = self.client.get(url, follow=True)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "fixed-bottom bg-white border-top shadow-sm",
                                    msg_prefix=f"Client footer missing on {url}")
                
# Template Content Verification Test - LLW 301
class TemplateContentVerificationTest(TestCase):
    def setUp(self):
        self.client = Client()

        # Required by home, practice area, and about views
        self.content = WebsiteContent.objects.create(
            frontPageHeader="Test Header",
            frontPageDescription="Test Description",
        )

        # 4 FAQ pairs 
        FAQItem.objects.create(question="Question 1", answer="Answer 1", display_order=1, is_active=True)
        FAQItem.objects.create(question="Question 2", answer="Answer 2", display_order=2, is_active=True)
        FAQItem.objects.create(question="Question 3", answer="Answer 3", display_order=3, is_active=True)
        FAQItem.objects.create(question="Question 4", answer="Answer 4", display_order=4, is_active=True)

    # Home page
    def test_home_page_contains_faq_section(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Frequently Asked Questions")
        self.assertContains(response, "faqAccordion")

    def test_home_page_conatins_four_faq_pairs(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Question 1")
        self.assertContains(response, "Answer 1")
        self.assertContains(response, "Question 2")
        self.assertContains(response, "Answer 2")
        self.assertContains(response, "Question 3")
        self.assertContains(response, "Answer 3")
        self.assertContains(response, "Question 4")
        self.assertContains(response, "Answer 4")
    
    def test_home_page_contains_services_list_with_practice_area_links(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)

        # 5 Service img buttons link to practice areas
        self.assertContains(response, "Step-Parent Adoption")
        self.assertContains(response, "Adult Adoption")
        self.assertContains(response, "Guardianship")
        self.assertContains(response, "Guardianship to Adoption")
        self.assertContains(response, "Independent Adoption")
        self.assertContains(response, "practice-areas")

    def test_home_page_contains_map_section(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)

        # Google maps iframe is always present regardless of API key value
        self.assertContains(response, "google.com/maps/embed")
        self.assertContains(response, "601+University+Ave+Sacramento+CA")        

    # About Page
    def test_about_page_loads(self):
        response = self.client.get(reverse("about"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "About Lydia A. Suprun")

    def test_about_page_has_image_placeholder(self):
        response = self.client.get(reverse("about"))
        # Photo is commented out = verify img container is present
        response = self.client.get(reverse("about"))
        self.assertContains(response, "about-image")

    def test_about_page_contains_linkedin_link(self):
        response = self.client.get(reverse("about"))
        self.assertContains(response, "linkedin.com/in/lydia-suprun")

    # Practice Areas Page
    def test_practice_areas_page_contains_contact_links(self):
        response = self.client.get(reverse("practice_areas"))
        self.assertEqual(response.status_code, 200)
        # 'Book Appointment' button links to contact page
        self.assertContains(response, reverse("contact"))
        self.assertContains(response, "Book Appointment")

# CUSTOM DECORATORS AND UTILITIES TEST - LLW-304 *****
class SuperuserRequiredDecoratorTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        # A simple view to wrap with the decorator
        @superuser_required
        def dummy_view(request):
            from django.http import HttpResponse
            return HttpResponse("OK")
        self.dummy_view = dummy_view

        # Regular client user - not staff, not superuser, not ADMIN role
        self.regular_user = User.objects.create_user(
            email="regular@test.com",
            password="Pass123!",
            role=User.Role.CLIENT,
            is_active=True,
        )

        # Superuser
        self.superuser = User.objects.create_user(
            email="super@test.com",
            password="Pass123!",
            role=User.Role.ADMIN,
            is_active=True,
            is_staff=True,
            is_superuser=True,
        )

        # Staff user (is_staff=True but not superuser)
        self.staff_user = User.objects.create_user(
            email="staff@test.com",
            password="Pass123!",
            role=User.Role.ADMIN,
            is_active=True,
            is_staff=True,
        )

        # Admin role user
        self.admin_role_user = User.objects.create_user(
            email="adminrole@test.com",
            password="Pass123!",
            role=User.Role.ADMIN,
            is_active=True,
        )

    def _make_request(self, user):
        request = self.factory.get("/fake-url/")
        request.user = user
        return request
    
    # --- Should be blocked (403) ---
    def test_unauthenticated_user_gets_403(self):
        """Unauthenticated users should be denied."""
        from django.contrib.auth.models import AnonymousUser
        request = self.factory.get("/fake-url/")
        request.user = AnonymousUser()
        with self.assertRaises(PermissionDenied):
            self.dummy_view(request)

    def test_regular_client_user_gets_403(self):
        """A regular client user should be denied."""
        request = self._make_request(self.regular_user)
        with self.assertRaises(PermissionDenied):
            self.dummy_view(request)

    # --- Should be allowed through ---
    def test_superuser_is_allowed(self):
        """A superuser should pass through the decorator."""
        request = self._make_request(self.superuser)
        response = self.dummy_view(request)
        self.assertEqual(response.status_code, 200)

    def test_staff_user_is_allowed(self):
        """A staff user (is_staff=True) should pass through the decorator."""
        request = self._make_request(self.staff_user)
        response = self.dummy_view(request)
        self.assertEqual(response.status_code, 200)

    def test_admin_role_user_is_allowed(self):
        """A user with role=ADMIN should pass through the decorator."""
        request = self._make_request(self.admin_role_user)
        response = self.dummy_view(request)
        self.assertEqual(response.status_code, 200)

class FormatPhoneFilterTest(TestCase):
    def _render(self, value):
        """Helper: render {{ value|format_phone }} and return the string."""
        t = Template("{% load phone_filter %}{{ value|format_phone }}")
        return t.render(Context({"value": value}))
    
    # --- 10-digit formatting ---
    def test_10_digit_number_formats_correctly(self):
        """10-digit number should be formatted as (XXX) XXX-XXXX."""
        result = self._render("9165551234")
        self.assertEqual(result, "(916) 555 - 1234")

    def test_10_digit_number_with_dashes(self):
        """Dashes should be stripped and number formatted correctly."""
        result = self._render("916-555-1234")
        self.assertEqual(result, "(916) 555 - 1234")

    def test_10_digit_number_with_parentheses(self):
        """Parentheses and spaces should be stripped and formatted correctly."""
        result = self._render("(916) 555-1234")
        self.assertEqual(result, "(916) 555 - 1234")

    # --- Non-10-digit: return raw value ---
    def test_short_number_returns_raw_value(self):
        """Numbers with fewer than 10 digits should return the raw value."""
        result = self._render("12345")
        self.assertEqual(result, "12345")

    def test_long_number_returns_raw_value(self):
        """Numbers with more than 10 digits should return the raw value."""
        result = self._render("19165551234")
        self.assertEqual(result, "19165551234")

    # --- Empty / None ---
    def test_empty_string_returns_placeholder(self):
        """Empty string should return '--'."""
        result = self._render("")
        self.assertEqual(result, "--")
        
    def test_none_returns_placeholder(self):
        """None should return '--'."""
        t = Template("{% load phone_filter %}{{ value|format_phone }}")
        result = t.render(Context({"value": None}))
        self.assertEqual(result, "--")


############################### Admin Dashboard (LLW-287) ###############################

class AdminDashboardTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="pw",
            first_name="Admin",
            last_name="User",
            is_staff=True,
            is_active=True,
        )
        self.non_admin = User.objects.create_user(
            email="client@example.com",
            password="pw",
            is_staff=False,
            is_active=True,
        )
        self.url = reverse("admin_dashboard")

    # --- A) Superuser required ---

    def test_unauthenticated_gets_403(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_non_admin_gets_403(self):
        self.client.force_login(self.non_admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_admin_gets_200(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_uses_dashboard_template(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, "admin/dashboard.html")

    # --- B) Calendar / content context ---

    def test_dashboard_passes_upcoming_appts_context(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertIn("upcoming_appts", response.context)

    def test_dashboard_passes_content_context(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertIn("content", response.context)

    def test_dashboard_renders_calendar_section(self):
        '''
        IMPORTANT - this test will fail until we embed calendly in the dashboard (scheduled for sprint 10)
        '''
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertContains(response, "calendly-inline-widget")

    # --- C) Next 3 upcoming appointments with date/time/location ---

    def _create_future_appointments(self, count, base_user=None):
        if base_user is None:
            base_user = self.non_admin
        now = timezone.now()
        for i in range(count):
            Appointments.objects.create(
                user_id=base_user,
                start_time=now + timedelta(days=i + 1),
                status=Appointments.Status.CONFIRMED,
            )

    def test_dashboard_shows_upcoming_appointments_in_context(self):
        self._create_future_appointments(3)
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(len(response.context["upcoming_appts"]), 3)

    def test_dashboard_caps_upcoming_at_5(self):
        self._create_future_appointments(6)
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertLessEqual(len(response.context["upcoming_appts"]), 5)

    def test_dashboard_renders_appointment_date_time(self):
        self._create_future_appointments(1)
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertContains(response, "Upcoming Appointments")

    def test_dashboard_renders_appointment_location(self):
        self._create_future_appointments(1)
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertContains(response, "In Office")

    def test_dashboard_renders_appointment_status_badge(self):
        self._create_future_appointments(1)
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertContains(response, "Confirmed")

    def test_cancelled_appointments_excluded_from_upcoming(self):
        now = timezone.now()
        Appointments.objects.create(
            user_id=self.non_admin,
            start_time=now + timedelta(days=1),
            status=Appointments.Status.CANCELLED,
            cancellation_reason="Cancelled for test",
            cancelled_at=now,
        )
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(len(response.context["upcoming_appts"]), 0)

    # --- D) Empty state ---

    def test_dashboard_empty_state_message(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertContains(response, "no upcoming appointments")


############################### Edge Cases and Error Handling (LLW-305) ###############################

class EdgeCasesTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@edge.com",
            password="pw",
            is_staff=True,
            is_active=True,
        )
        self.non_admin = User.objects.create_user(
            email="nonadmin@edge.com",
            password="pw",
            is_staff=False,
            is_active=True,
        )

    # --- A) 404 for non-existent routes ---

    def test_nonexistent_route_returns_404(self):
        from django.test import override_settings
        with override_settings(DEBUG=False):
            response = self.client.get("/this-route-absolutely-does-not-exist-xyz/")
        self.assertEqual(response.status_code, 404)

    def test_404_page_contains_page_not_found(self):
        from django.test import override_settings
        with override_settings(DEBUG=False):
            response = self.client.get("/this-route-absolutely-does-not-exist-xyz/")
        self.assertContains(response, "Page Not Found", status_code=404)

    def test_404_page_has_go_home_link(self):
        from django.test import override_settings
        with override_settings(DEBUG=False):
            response = self.client.get("/this-route-absolutely-does-not-exist-xyz/")
        self.assertContains(response, "Go Home", status_code=404)

    def test_404_page_shows_error_code(self):
        from django.test import override_settings
        with override_settings(DEBUG=False):
            response = self.client.get("/this-route-absolutely-does-not-exist-xyz/")
        self.assertContains(response, "404", status_code=404)

    # --- B) 403 page styling / content ---

    def test_403_page_shows_permission_denied(self):
        response = self.client.get(reverse("admin_dashboard"))
        self.assertContains(response, "Permission Denied", status_code=403)

    def test_403_page_unauthenticated_shows_not_signed_in(self):
        response = self.client.get(reverse("admin_dashboard"))
        self.assertContains(response, "not signed in", status_code=403)

    def test_403_page_unauthenticated_has_sign_in_link(self):
        response = self.client.get(reverse("admin_dashboard"))
        self.assertContains(response, "Sign In", status_code=403)

    def test_403_page_authenticated_shows_user_email(self):
        self.client.force_login(self.non_admin)
        response = self.client.get(reverse("admin_dashboard"))
        self.assertContains(response, "nonadmin@edge.com", status_code=403)

    def test_403_page_has_go_home_button(self):
        response = self.client.get(reverse("admin_dashboard"))
        self.assertContains(response, "Go Home", status_code=403)

    def test_403_page_shows_error_code_403(self):
        response = self.client.get(reverse("admin_dashboard"))
        self.assertContains(response, "403", status_code=403)

    # --- C) Empty state: admin dashboard with no appointments ---

    def test_admin_dashboard_empty_state(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin_dashboard"))
        self.assertEqual(len(response.context["upcoming_appts"]), 0)
        self.assertContains(response, "no upcoming appointments")

    # --- D) Empty state: transaction history with no transactions ---

    def test_client_invoices_empty_state(self):
        self.client.force_login(self.non_admin)
        response = self.client.get(reverse("client_invoices"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No past invoices")

    # --- E) Empty state: admin clients with no clients ---

    def test_admin_clients_empty_state(self):
        # No CLIENT role users created — page_obj must be empty
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin_clients"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"]), 0)

    # --- F) Appointment for past date: excluded from upcoming ---

    def test_past_appointment_excluded_from_admin_dashboard(self):
        Appointments.objects.create(
            user_id=self.non_admin,
            start_time=timezone.now() - timedelta(days=1),
            status=Appointments.Status.CONFIRMED,
        )
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin_dashboard"))
        self.assertEqual(len(response.context["upcoming_appts"]), 0)

    def test_past_appointment_excluded_from_client_dashboard(self):
        Appointments.objects.create(
            user_id=self.non_admin,
            start_time=timezone.now() - timedelta(days=1),
            status=Appointments.Status.CONFIRMED,
        )
        self.client.force_login(self.non_admin)
        response = self.client.get(reverse("client_dashboard"))
        self.assertEqual(len(response.context["upcoming_appts"]), 0)
