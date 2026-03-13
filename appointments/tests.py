from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from django.core.exceptions import ValidationError

from appointments.models import Appointments
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