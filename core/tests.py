from datetime import timedelta

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointments, Invitee
from users.models import User


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