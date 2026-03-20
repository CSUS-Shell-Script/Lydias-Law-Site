from datetime import timedelta
from datetime import timedelta

from django.contrib.messages import get_messages
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.utils import timezone

from sitecontent.models import WebsiteContent
from appointments.models import Appointments, Invitee
from users.models import User
from django.contrib.auth import get_user_model
from finances.models import Invoice
from allauth.account.models import EmailAddress

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

    # Test: About page returns 200
    def test_about_page_returns_200(self):
        response = self.client.get(reverse('about'))
        self.assertEqual(response.status_code, 200)

    # Test: About page conatins biography
    def test_about_page_contains_biography_section(self):
        response = self.client.get(reverse('about'))
        self.assertContains(response, 'About Lydia A. Suprun')

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

    # Test: Contact page returns 200
    def test_contact_page_returns_200(self):
        response = self.client.get(reverse('contact'))
        self.assertEqual(response.status_code, 200)

    # Test: Payment (invoice lookup) page returns 200
    def test_payment_page_returns_200(self):
        response = self.client.get(reverse('payment'))
        self.assertEqual(response.status_code, 200)

    # Test: Privacy page returns 200
    def test_privacy_page_returns_200(self):
        response = self.client.get(reverse('privacy'))
        self.assertEqual(response.status_code, 200)

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

############################### Admin pages ###############################

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

