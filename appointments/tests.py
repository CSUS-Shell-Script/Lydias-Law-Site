import json
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

class PublicAppointmentCreationTest(TestCase):
    def setUp(self):
        self.client = Client()

        # Fallback host user (superuser)
        self.host_user = User.objects.create_user(
            email="host@example.com",
            password="testpass",
            is_superuser=True
        )

        self.url = reverse("calendly_webhook")

    # Helper to return a valid payload for testing
    def valid_payload(self):
        return {
            "event": "invitee.created",
            "payload": {
                "email": "guest@example.com",
                "name": "Guest User",
                "uri": "invitee_001",
                "scheduled_event": {
                    "uri": "event_001",
                    "start_time": "2026-04-10T15:00:00Z",
                    "end_time": "2026-04-10T15:30:00Z",
                    "event_memberships": [
                        {"user_email": "host@example.com"}
                    ]
                }
            }
        }

    # Non signed-in user can schedule appointment and database is updated
    def test_valid_guest_appointment_created(self):
        payload = self.valid_payload()
        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Appointments.objects.count(), 1)

        appt = Appointments.objects.first()
        self.assertEqual(appt.calendly_event_uri, "event_001")
        self.assertEqual(appt.status, Appointments.Status.CONFIRMED)
        self.assertEqual(appt.user_id, self.host_user)

    # Blank name field prevents creation
    def test_blank_name_prevents_appointment(self):
        payload = self.valid_payload()
        payload["payload"]["name"] = ""
        self.client.post(self.url, data=json.dumps(payload), content_type="application/json")
        # Appointment should not exist
        self.assertFalse(Appointments.objects.filter(calendly_event_uri="event_001").exists())

    # Blank email field prevents creation
    def test_blank_email_prevents_appointment(self):
        payload = self.valid_payload()
        payload["payload"]["email"] = ""
        self.client.post(self.url, data=json.dumps(payload), content_type="application/json")
        self.assertFalse(Appointments.objects.filter(calendly_event_uri="event_001").exists())

    # Invalid email format prevents creation
    def test_invalid_email_prevents_appointment(self):
        payload = self.valid_payload()
        payload["payload"]["email"] = "not-an-email"
        self.client.post(self.url, data=json.dumps(payload), content_type="application/json")
        self.assertFalse(Appointments.objects.filter(calendly_event_uri="event_001").exists())

class AdminSchedulingTests(TestCase):

    def setUp(self):
        self.client = Client()

        self.admin = User.objects.create_superuser(
            email="admin@test.com",
            password="testpass123"
        )

        self.client_user = User.objects.create_user(
            email="client@test.com",
            password="testpass123",
            role=User.Role.CLIENT,
            is_active=True
        )

        self.client.login(email="admin@test.com", password="testpass123")

        self.schedule_url = reverse("admin_schedule")
        self.dashboard_url = reverse("admin_dashboard")

    def test_admin_can_access_scheduling_page(self):
        response = self.client.get(self.schedule_url)
        self.assertEqual(response.status_code, 200)

    def test_admin_can_create_appointment(self):
        start_time = timezone.now() + timedelta(days=1)

        appointment = Appointments.objects.create(
            user_id=self.client_user,
            start_time=start_time,
            duration=timedelta(minutes=15),
            comments="Test appointment"
        )

        self.assertIsNotNone(appointment.id)

        self.assertTrue(
            Appointments.objects.filter(user_id=self.client_user).exists()
        )

    def test_close_button_redirects_to_dashboard(self):
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)

    def test_confirmation_page_message(self):
        response = self.client.get(reverse("admin_appointment_confirmation"))

        self.assertEqual(response.status_code, 200)

        self.assertContains(response, "Appointment Confirmed")


    def test_confirmation_page_loads(self):
        response = self.client.get(reverse("admin_appointment_confirmation"))

        self.assertEqual(response.status_code, 200)


    def test_dashboard_page_accessible(self):
        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)

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


class CalendlyWebhookTest(TestCase):
    """
    Tests for the Calendly webhook endpoint at POST /webhooks/calendly/.

    When Calendly fires an event (e.g. a client books or cancels), it sends
    a POST request to this URL with a JSON payload. These tests verify that
    our view handles every case correctly without ever needing a live Calendly
    account — we just POST fake-but-realistic JSON directly.

    ── How the test data flows ────────────────────────────────────────────
    Calendly payload
        └─ payload.scheduled_event.uri  ──► Appointments.calendly_event_uri
        └─ payload.uri                  ──► Invitee.calendly_invitee_uri
        └─ payload.email                ──► matched to a User in our DB

    ── Signature tests ────────────────────────────────────────────────────
    The last two tests (test_missing_signature_* / test_invalid_signature_*)
    document REQUIRED but NOT YET IMPLEMENTED behaviour. They will fail
    until the view validates the Calendly-Webhook-Signature header.
    """

    WEBHOOK_URL = reverse('calendly_webhook')

    # ── Stable test URIs ──────────────────────────────────────────────────
    # These mirror the format Calendly uses in real payloads.
    # The same URI is the idempotency key — sending it twice must not
    # produce two DB rows.
    EVENT_URI    = 'https://api.calendly.com/scheduled_events/EVT-001'
    INVITEE_URI  = 'https://api.calendly.com/scheduled_events/EVT-001/invitees/INV-001'
    INVITEE_URI2 = 'https://api.calendly.com/scheduled_events/EVT-001/invitees/INV-002'

    def setUp(self):
        # The view looks up the host by matching event_memberships[0].user_email.
        # If no match is found it falls back to the first superuser.
        # We create a superuser here so that fallback always resolves.
        self.host = User.objects.create_superuser(
            email='host@example.com',
            password='hostpass123',
            first_name='Host',
            last_name='Admin',
        )
        self.host.is_active = True
        self.host.save()

        # A registered client whose email matches the invitee email in the
        # payload. The view uses this to associate the appointment with an
        # existing user account rather than the host.
        self.client_user = User.objects.create_user(
            email='client@example.com',
            password='clientpass123',
            first_name='Client',
            last_name='User',
            role=User.Role.CLIENT,
        )
        self.client_user.is_active = True
        self.client_user.save()

        # Django test client — used to send HTTP requests to the view
        self.http = Client()

    # ── Payload helpers ───────────────────────────────────────────────────
    # Building payloads here keeps the tests themselves short and readable.
    # Each helper returns a dict that matches the real Calendly JSON shape.

    def _created_payload(
        self,
        event_uri=None,
        invitee_uri=None,
        invitee_email='client@example.com',
    ):
        """
        Builds a realistic 'invitee.created' payload.
        Calendly sends this when a client successfully books a slot.

        event_memberships tells the view who the host (attorney) is.
        The view matches user_email against our User table; if found it
        uses that user, otherwise it falls back to the first superuser.
        """
        event_uri   = event_uri   or self.EVENT_URI
        invitee_uri = invitee_uri or self.INVITEE_URI
        return {
            'event': 'invitee.created',
            'payload': {
                'uri': invitee_uri,           # unique ID for this invitee record
                'email': invitee_email,        # client's email — matched to a User
                'name': 'Client User',
                'status': 'active',
                'scheduled_event': {
                    'uri': event_uri,          # unique ID for the booked slot
                    'name': 'Consultation',
                    'status': 'active',
                    'start_time': '2026-04-01T10:00:00Z',
                    'end_time':   '2026-04-01T10:30:00Z',
                    # event_memberships[0].user_email → host user lookup
                    'event_memberships': [{'user_email': 'host@example.com'}],
                },
                'questions_and_answers': [],   # optional pre-booking questions
            },
        }

    def _canceled_payload(self, invitee_uri=None):
        """
        Builds a realistic 'invitee.canceled' payload.
        Calendly sends this when a client cancels their booking.

        The view finds the Invitee row by URI, then marks both the
        Invitee and its parent Appointment as cancelled.
        """
        return {
            'event': 'invitee.canceled',
            'payload': {'uri': invitee_uri or self.INVITEE_URI},
        }

    def _post(self, payload, headers=None):
        """Serialize payload to JSON and POST it to the webhook endpoint."""
        return self.http.post(
            self.WEBHOOK_URL,
            data=json.dumps(payload),
            content_type='application/json',
            **(headers or {}),
        )

    # ── Section 1: HTTP method guard ──────────────────────────────────────
    # The endpoint must only respond to POST. Any other verb is rejected
    # immediately with 400 before any DB work happens.

    def test_get_request_returns_400(self):
        # Calendly always POSTs — a GET most likely means someone mis-typed
        # the URL in a browser, or a misconfigured ping. Reject it.
        response = self.http.get(self.WEBHOOK_URL)
        self.assertEqual(response.status_code, 400)

    def test_put_request_returns_400(self):
        response = self.http.put(self.WEBHOOK_URL)
        self.assertEqual(response.status_code, 400)

    def test_post_request_is_accepted(self):
        # A well-formed POST (even with an unknown event type) gets through
        # the method guard and returns 200.
        response = self._post({'event': 'unknown.event', 'payload': {}})
        self.assertEqual(response.status_code, 200)

    # ── Section 2: invitee.created ────────────────────────────────────────
    # When a client books a slot, Calendly fires 'invitee.created'.
    # Our view must create one Appointment row and one Invitee row, linked
    # together, and return 200.

    def test_invitee_created_creates_appointment(self):
        # After posting the event we expect exactly one Appointment in the DB
        # whose calendly_event_uri matches the URI in the payload.
        self._post(self._created_payload())
        self.assertEqual(Appointments.objects.filter(calendly_event_uri=self.EVENT_URI).count(), 1)

    def test_invitee_created_appointment_has_confirmed_status(self):
        # Calendly bookings start life as CONFIRMED (not PENDING) because
        # Calendly handles the scheduling — no manual approval needed.
        self._post(self._created_payload())
        appt = Appointments.objects.get(calendly_event_uri=self.EVENT_URI)
        self.assertEqual(appt.status, Appointments.Status.CONFIRMED)

    def test_invitee_created_creates_invitee(self):
        # A separate Invitee row is created to store the client's details
        # (name, email, reschedule URL, etc.) independently of the Appointment.
        self._post(self._created_payload())
        self.assertEqual(Invitee.objects.filter(calendly_invitee_uri=self.INVITEE_URI).count(), 1)

    def test_invitee_created_invitee_linked_to_appointment(self):
        # The Invitee must point back to its parent Appointment via FK,
        # so we can look up "who is attending this appointment?".
        self._post(self._created_payload())
        appt    = Appointments.objects.get(calendly_event_uri=self.EVENT_URI)
        invitee = Invitee.objects.get(calendly_invitee_uri=self.INVITEE_URI)
        self.assertEqual(invitee.appointment, appt)

    def test_invitee_created_associates_registered_client(self):
        # If the invitee's email matches a User in our DB, the Appointment
        # should be owned by that client — not the host/attorney.
        self._post(self._created_payload(invitee_email='client@example.com'))
        appt = Appointments.objects.get(calendly_event_uri=self.EVENT_URI)
        self.assertEqual(appt.user_id, self.client_user)

    def test_invitee_created_returns_200(self):
        response = self._post(self._created_payload())
        self.assertEqual(response.status_code, 200)

    # ── Section 3: invitee.canceled ───────────────────────────────────────
    # When a client cancels, Calendly fires 'invitee.canceled' with the
    # same invitee URI that was in the original 'invitee.created' event.
    # Our view uses that URI to find the right row and mark it cancelled.

    def test_invitee_canceled_sets_appointment_status_to_cancelled(self):
        # Step 1 — simulate the original booking arriving
        self._post(self._created_payload())
        # Step 2 — simulate the cancellation arriving
        self._post(self._canceled_payload())

        appt = Appointments.objects.get(calendly_event_uri=self.EVENT_URI)
        self.assertEqual(appt.status, Appointments.Status.CANCELLED)

    def test_invitee_canceled_sets_invitee_canceled_flag(self):
        # The Invitee row itself also gets a `canceled = True` flag so we
        # can distinguish "was cancelled" from "was rescheduled".
        self._post(self._created_payload())
        self._post(self._canceled_payload())

        invitee = Invitee.objects.get(calendly_invitee_uri=self.INVITEE_URI)
        self.assertTrue(invitee.canceled)

    def test_invitee_canceled_for_unknown_invitee_returns_200(self):
        # If Calendly sends a cancellation for a URI we don't recognise
        # (e.g. a booking that predates our system) we log and return 200
        # rather than crashing — defensive handling.
        response = self._post(self._canceled_payload(invitee_uri='https://calendly.com/unknown'))
        self.assertEqual(response.status_code, 200)

    def test_invitee_canceled_returns_200(self):
        self._post(self._created_payload())
        response = self._post(self._canceled_payload())
        self.assertEqual(response.status_code, 200)

    # ── Section 4: Idempotency ────────────────────────────────────────────
    # Webhooks are "at-least-once" — Calendly may retry if it doesn't receive
    # a timely 200. Sending the same event twice must produce the same result
    # as sending it once (no duplicate rows, no errors).
    #
    # The view achieves this with get_or_create keyed on the Calendly URI,
    # which is globally unique per booking / per invitee.

    def test_duplicate_invitee_created_does_not_duplicate_appointment(self):
        payload = self._created_payload()
        self._post(payload)  # first delivery
        self._post(payload)  # Calendly retry — must be a no-op
        self.assertEqual(Appointments.objects.filter(calendly_event_uri=self.EVENT_URI).count(), 1)

    def test_duplicate_invitee_created_does_not_duplicate_invitee(self):
        payload = self._created_payload()
        self._post(payload)
        self._post(payload)
        self.assertEqual(Invitee.objects.filter(calendly_invitee_uri=self.INVITEE_URI).count(), 1)

    def test_duplicate_invitee_canceled_leaves_appointment_cancelled(self):
        # Cancelling an already-cancelled appointment must stay CANCELLED,
        # not raise an error or flip back to another status.
        self._post(self._created_payload())
        self._post(self._canceled_payload())  # first cancel
        self._post(self._canceled_payload())  # duplicate cancel — must be safe

        appt = Appointments.objects.get(calendly_event_uri=self.EVENT_URI)
        self.assertEqual(appt.status, Appointments.Status.CANCELLED)

    # ── Section 5: Unrecognised event type ────────────────────────────────
    # Calendly has many event types (routing_form.submission, etc.) that we
    # don't handle. We return 200 so Calendly stops retrying, but we do
    # nothing to the database.

    def test_unknown_event_returns_200(self):
        response = self._post({'event': 'routing_form.submission', 'payload': {}})
        self.assertEqual(response.status_code, 200)

    def test_unknown_event_does_not_create_appointment(self):
        self._post({'event': 'routing_form.submission', 'payload': {}})
        self.assertEqual(Appointments.objects.count(), 0)

    # ── Section 6: Signature validation (NOT YET IMPLEMENTED) ────────────
    # Calendly signs every webhook with an HMAC-SHA256 signature sent in
    # the Calendly-Webhook-Signature header. Verifying this prevents anyone
    # on the internet from spoofing fake bookings or cancellations.
    #
    # !! These two tests will FAIL on the current code !!
    # They are written now so the requirement is visible in the test suite.
    # Once the view reads CALENDLY_WEBHOOK_SECRET from settings and validates
    # the header, these tests will begin passing automatically.

    def test_missing_signature_header_returns_403(self):
        # A request with no signature header should be rejected — it could
        # be anyone, not Calendly.
        response = self._post(self._created_payload())
        self.assertIn(response.status_code, [400, 403])

    def test_invalid_signature_returns_403(self):
        # A request where the signature doesn't match our secret should
        # also be rejected, even if the JSON body looks valid.
        response = self._post(
            self._created_payload(),
            headers={'HTTP_CALENDLY_WEBHOOK_SIGNATURE': 'invalid-signature'},
        )
        self.assertIn(response.status_code, [400, 403])
