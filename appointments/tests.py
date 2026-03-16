import string

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from appointments.models import Appointments, Invitee, Notification
from users.models import User

class ClientAppointmentCreationTest(TestCase):
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
        
        # Store URLs
        self.dashboard_url = reverse('client_dashboard')
        self.login_url = reverse('login')

    # Test that users must be signed in to access the scheduling page
    def test_dashboard_requires_authentication(self):
        # Try to access dashboard without authentication
        response = self.client.get(self.dashboard_url)
        
        # Should redirect to login
        expected_url = f"{self.login_url}?next={self.dashboard_url}"
        self.assertRedirects(response, expected_url)
        
        # Login and verify access works
        self.client.login(username='client@example.com', password='testpass123')
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'client/dashboard.html')

    # Test that appointment dates are properly stored
    def test_appointment_date_validation(self):
        self.client.login(username='client@example.com', password='testpass123')
        
        # Test with future date (valid)
        future_date = timezone.now() + timedelta(days=2)
        appointment = Appointments.objects.create(
            user_id=self.client_user,
            start_time=future_date,
            comments="Future appointment",
            status=Appointments.Status.PENDING
        )
        
        # Verify date was saved correctly
        saved_appointment = Appointments.objects.get(id=appointment.id)
        self.assertEqual(saved_appointment.start_time.date(), future_date.date())

    # Test that required fields cannot be null
    def test_required_fields_validation(self):
        # Test missing user (should fail)
        with self.assertRaises(Exception):
            Appointments.objects.create(
                # Missing user_id
                start_time=timezone.now() + timedelta(days=2),
                status=Appointments.Status.PENDING
            )
        
        # Test missing start_time (should fail)
        with self.assertRaises(Exception):
            Appointments.objects.create(
                user_id=self.client_user,
                # Missing start_time
                status=Appointments.Status.PENDING
            )

    # Test that only minimal required fields are needed to create an appointment
    def test_minimal_required_fields_for_appointment(self):
        # Create appointment with only absolutely required fields
        appointment = Appointments.objects.create(
            user_id=self.client_user,
            start_time=timezone.now() + timedelta(days=3),
            status=Appointments.Status.PENDING
        )
        
        # Verify appointment was created
        self.assertIsNotNone(appointment.id)
        self.assertEqual(appointment.user_id, self.client_user)
        self.assertEqual(appointment.status, Appointments.Status.PENDING)
        
        # Optional fields should be null/blank
        self.assertIsNone(appointment.comments)
        self.assertIsNone(appointment.calendly_event_name)
        self.assertIsNone(appointment.calendly_event_uri)

    # Test that new appointments have PENDING status
    def test_appointment_created_with_pending_status(self):
        appointment = Appointments.objects.create(
            user_id=self.client_user,
            start_time=timezone.now() + timedelta(days=5),
            comments="New consultation"
            # Status not specified - should use default
        )
        
        # Refresh from database
        appointment.refresh_from_db()
        
        # Verify default status is PENDING
        self.assertEqual(appointment.status, Appointments.Status.PENDING)

    # Test that PENDING appointments show up in the dashboard
    def test_pending_appointments_appear_in_dashboard(self):
        # Create a PENDING appointment
        appointment = Appointments.objects.create(
            user_id=self.client_user,
            start_time=timezone.now() + timedelta(days=2),
            comments="Dashboard test appointment",
            status=Appointments.Status.PENDING
        )
        
        # Login and check dashboard
        self.client.login(username='client@example.com', password='testpass123')
        response = self.client.get(self.dashboard_url)
        
        # Check context
        self.assertIn('upcoming_appts', response.context)
        upcoming = response.context['upcoming_appts']
        
        # Find our appointment
        matching = [a for a in upcoming if a.id == appointment.id]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].status, Appointments.Status.PENDING)
        
        # Check HTML
        content = response.content.decode()
        self.assertIn('Dashboard test appointment', content)
        self.assertIn('Pending', content)

    # Test that the appointment confirmation page is accessible
    def test_confirmation_page_accessible(self):
        self.client.login(username='client@example.com', password='testpass123')
        
        # Get the confirmation page (this is where Calendly redirects after scheduling)
        confirmation_url = reverse('client_appointment_confirmation')
        response = self.client.get(confirmation_url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'client/appointment_confirmation.html')


class AppointmentModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='model@example.com',
            password='testpass123',
            first_name='Model',
            last_name='Test',
            role=User.Role.CLIENT,
        )
        self.user.is_active = True
        self.user.save()

    def make_appointment(self, **kwargs):
        defaults = dict(
            user_id=self.user,
            start_time=timezone.now() + timedelta(days=1),
        )
        defaults.update(kwargs)
        return Appointments.objects.create(**defaults)

    # --- Confirmation number ---

    def test_confirmation_number_auto_generated_on_create(self):
        appt = self.make_appointment()
        self.assertIsNotNone(appt.confirmation_number)

    def test_confirmation_number_is_8_characters(self):
        appt = self.make_appointment()
        self.assertIsNotNone(appt.confirmation_number)
        self.assertEqual(len(appt.confirmation_number), 8)  # type: ignore[arg-type]

    def test_confirmation_number_is_uppercase_alphanumeric(self):
        appt = self.make_appointment()
        self.assertIsNotNone(appt.confirmation_number)
        allowed = set(string.ascii_uppercase + string.digits)
        self.assertTrue(all(c in allowed for c in appt.confirmation_number))  # type: ignore[union-attr]

    def test_confirmation_numbers_are_unique_across_appointments(self):
        appt1 = self.make_appointment()
        appt2 = self.make_appointment()
        self.assertNotEqual(appt1.confirmation_number, appt2.confirmation_number)

    def test_duplicate_confirmation_number_raises_integrity_error(self):
        appt = self.make_appointment()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_appointment(confirmation_number=appt.confirmation_number)

    # --- Valid status transitions ---

    def test_pending_can_transition_to_confirmed(self):
        self.assertTrue(Appointments.can_transition_status(
            Appointments.Status.PENDING, Appointments.Status.CONFIRMED
        ))

    def test_pending_can_transition_to_cancelled(self):
        self.assertTrue(Appointments.can_transition_status(
            Appointments.Status.PENDING, Appointments.Status.CANCELLED
        ))

    def test_confirmed_can_transition_to_completed(self):
        self.assertTrue(Appointments.can_transition_status(
            Appointments.Status.CONFIRMED, Appointments.Status.COMPLETED
        ))

    def test_confirmed_can_transition_to_no_show(self):
        self.assertTrue(Appointments.can_transition_status(
            Appointments.Status.CONFIRMED, Appointments.Status.NO_SHOW
        ))

    def test_confirmed_can_transition_to_cancelled(self):
        self.assertTrue(Appointments.can_transition_status(
            Appointments.Status.CONFIRMED, Appointments.Status.CANCELLED
        ))

    # --- Invalid status transitions ---

    def test_completed_cannot_transition_to_pending(self):
        self.assertFalse(Appointments.can_transition_status(
            Appointments.Status.COMPLETED, Appointments.Status.PENDING
        ))

    def test_cancelled_cannot_transition_to_pending(self):
        self.assertFalse(Appointments.can_transition_status(
            Appointments.Status.CANCELLED, Appointments.Status.PENDING
        ))

    def test_no_show_cannot_transition_to_confirmed(self):
        self.assertFalse(Appointments.can_transition_status(
            Appointments.Status.NO_SHOW, Appointments.Status.CONFIRMED
        ))

    def test_pending_cannot_skip_to_completed(self):
        self.assertFalse(Appointments.can_transition_status(
            Appointments.Status.PENDING, Appointments.Status.COMPLETED
        ))

    def test_pending_cannot_skip_to_no_show(self):
        self.assertFalse(Appointments.can_transition_status(
            Appointments.Status.PENDING, Appointments.Status.NO_SHOW
        ))

    # --- Invitee ---

    def test_invitee_links_to_parent_appointment(self):
        appt = self.make_appointment()
        invitee = Invitee.objects.create(
            appointment=appt,
            name='Jane Doe',
            email='jane@example.com',
        )
        self.assertEqual(invitee.appointment, appt)
        self.assertIn(invitee, appt.invitees.all())

    def test_invitee_deleted_when_appointment_deleted(self):
        appt = self.make_appointment()
        invitee = Invitee.objects.create(
            appointment=appt,
            name='Jane Doe',
            email='jane@example.com',
        )
        invitee_id = invitee.id
        appt.delete()
        self.assertFalse(Invitee.objects.filter(id=invitee_id).exists())

    def test_multiple_invitees_can_link_to_one_appointment(self):
        appt = self.make_appointment()
        Invitee.objects.create(appointment=appt, name='Alice', email='alice@example.com')
        Invitee.objects.create(appointment=appt, name='Bob', email='bob@example.com')
        self.assertEqual(appt.invitees.count(), 2)

    # --- Cancellation ---

    def test_cancellation_stores_reason_and_timestamp(self):
        appt = self.make_appointment()
        cancel_time = timezone.now()
        appt.status = Appointments.Status.CANCELLED
        appt.cancellation_reason = 'Client request'
        appt.cancelled_at = cancel_time
        appt.save()
        appt.refresh_from_db()

        self.assertEqual(appt.status, Appointments.Status.CANCELLED)
        self.assertEqual(appt.cancellation_reason, 'Client request')
        self.assertIsNotNone(appt.cancelled_at)

    def test_cancellation_reason_and_cancelled_at_default_to_null(self):
        appt = self.make_appointment()
        self.assertIsNone(appt.cancellation_reason)
        self.assertIsNone(appt.cancelled_at)

    # --- Notification ---

    def test_notification_stores_channel_type_status(self):
        notif = Notification.objects.create(
            user=self.user,
            channel=Notification.Channel.EMAIL,
            type=Notification.Type.APPT_CONFIRM,
            status=Notification.Status.SENT,
        )
        notif.refresh_from_db()
        self.assertEqual(notif.channel, Notification.Channel.EMAIL)
        self.assertEqual(notif.type, Notification.Type.APPT_CONFIRM)
        self.assertEqual(notif.status, Notification.Status.SENT)

    def test_notification_default_status_is_sent(self):
        notif = Notification.objects.create(
            user=self.user,
            channel=Notification.Channel.SMS,
            type=Notification.Type.APPT_REMINDER,
        )
        self.assertEqual(notif.status, Notification.Status.SENT)

    def test_notification_failed_status_stored_correctly(self):
        notif = Notification.objects.create(
            user=self.user,
            channel=Notification.Channel.EMAIL,
            type=Notification.Type.INVOICE_ISSUED,
            status=Notification.Status.FAILED,
            error_message='SMTP timeout',
        )
        notif.refresh_from_db()
        self.assertEqual(notif.status, Notification.Status.FAILED)
        self.assertEqual(notif.error_message, 'SMTP timeout')

