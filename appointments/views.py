from datetime import timedelta
from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import redirect
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from core.decorators import superuser_required
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from .models import Appointments, Invitee
from .webhook_signature import verify_calendly_webhook_signature
from users.models import User
import json
import secrets



@csrf_exempt
def calendly_webhook(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")

    raw_body = request.body

    signing_key = (getattr(settings, "CALENDLY_WEBHOOK_KEY", "") or "").strip()
    if signing_key:
        sig = request.headers.get("Calendly-Webhook-Signature")
        if not verify_calendly_webhook_signature(raw_body, sig, signing_key):
            return HttpResponseForbidden("Invalid or missing Calendly webhook signature")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")

    event_type = payload.get("event")  # e.g. "invitee.created"
    data = payload.get("payload") or {}

    if event_type not in {"invitee.created", "invitee.canceled"}:
        return JsonResponse({"status": "ignored", "reason": "unsupported event"})
    
    if event_type == "invitee.created":
        # ---- Extract scheduled event + invitee data ----
        scheduled_event = data.get("scheduled_event", {})  # dict with event info
        invitee_uri = data.get("uri")                      # string

        if not scheduled_event:
            return HttpResponseBadRequest("Missing scheduled_event data")

        calendly_event_uri = scheduled_event.get("uri")
        if not calendly_event_uri:
            return HttpResponseBadRequest("Missing event uri")

         # ---- Validate Required Fields ----
        invitee_name = data.get("name", "").strip()
        invitee_email = data.get("email", "").strip()
        
        # Check for blank name
        if not invitee_name:
            return JsonResponse({"status": "rejected", "reason": "blank name"}, status=400)
        
        # Check for blank email
        if not invitee_email:
            return JsonResponse({"status": "rejected", "reason": "blank email"}, status=400)
        
        # Validate email format
        try:
            validate_email(invitee_email)
        except ValidationError:
            return JsonResponse({"status": "rejected", "reason": "invalid email format"}, status=400)
        
        # Start / end time
        start_time_str = scheduled_event.get("start_time")
        end_time_str = scheduled_event.get("end_time")

        start_time = parse_datetime(start_time_str) if start_time_str else None
        end_time = parse_datetime(end_time_str) if end_time_str else None
        duration = (end_time - start_time) if (start_time and end_time) else timedelta(minutes=30)

        # Calendly sends this in questions_and_answers, e.g. and parses into models.py/appointments_comments
        questions = data.get("questions_and_answers", []) or []
        comments = None
        for qa in questions:
            question_text = (qa.get("question") or "").lower()
            if "help prepare for our meeting" in question_text:
                comments = qa.get("answer")
                break
        # fallback: if no matching question text, use first answer if present
        if comments is None and questions:
            comments = questions[0].get("answer")

        # ---- Find the host user (attorney) from event_memberships ----
        event_memberships = scheduled_event.get("event_memberships", []) or []
        host_email = None
        if event_memberships:
            host_email = event_memberships[0].get("user_email")  # host calendly email

        host_user = None
        if host_email:
            host_user = User.objects.filter(email=host_email).first()

        # Fallback: first superuser (e.g., Lydia/admin)
        if host_user is None:
            host_user = User.objects.filter(is_superuser=True).first()

        if host_user is None:
            return HttpResponseBadRequest(
                "No host user found; create an admin user with the Calendly host email."
            )

        # ---- If the invitee is a registered user, use *their* user_id instead ----
        invitee_email = data.get("email")  # this is the client's email from Calendly
        client_user = None
        if invitee_email:
            client_user = User.objects.filter(email=invitee_email).first()

        # If matching client exists, associate appointment with them; otherwise with host
        appointment_user = client_user or host_user

        location = scheduled_event.get("location", {}) or {}

        # ---- Build defaults for new appointments (includes required user_id) ----
        defaults = {
            "user_id": appointment_user,
            "start_time": start_time,
            "duration": duration,
            "status": Appointments.Status.CONFIRMED,
            "calendar_api_id": calendly_event_uri,
            "comments": comments,  # <<< store Calendly comment here
            "calendly_event_name": scheduled_event.get("name"),
            "calendly_event_status": scheduled_event.get("status", "active"),
            "calendly_created_at": parse_datetime(scheduled_event.get("created_at"))
            if scheduled_event.get("created_at") else None,
            "calendly_updated_at": parse_datetime(scheduled_event.get("updated_at"))
            if scheduled_event.get("updated_at") else None,
            "calendly_location_type": location.get("type"),
            "calendly_join_url": location.get("join_url"),  # may be None for physical
            "calendly_organization_uri": None,
            "calendly_host_email": host_email,
        }

        # ---- Create or update Appointment ----
        appt, created = Appointments.objects.get_or_create(
            calendly_event_uri=calendly_event_uri,
            defaults=defaults,
        )

        if not created:
            # Update existing appointment with latest info (including comments)
            for field, value in defaults.items():
                # Only override comments if we actually got some text
                if field == "comments" and value is None:
                    continue
                setattr(appt, field, value)
            appt.save()

        # ---- Create Invitee record ----
        Invitee.objects.get_or_create(
            calendly_invitee_uri=invitee_uri,
            defaults={
                "appointment": appt,
                "name": data.get("name", ""),
                "email": invitee_email or "",
                "phone_number": data.get("text_reminder_number"),
                "status": data.get("status", "active"),
                "canceled": data.get("rescheduled", False),
                "cancellation_reason": None,
                "reschedule_url": data.get("reschedule_url"),
                "calendly_created_at": parse_datetime(data.get("created_at"))
                if data.get("created_at") else None,
                "calendly_updated_at": parse_datetime(data.get("updated_at"))
                if data.get("updated_at") else None,
            },
        )

    if event_type == "invitee.canceled":
        # Extract the invitee URI and appointment details.
        invitee_uri = data.get("uri")
        if not invitee_uri:
            return HttpResponseBadRequest("Missing invitee URI")

        # Find the invitee and associated appointment.
        invitee = Invitee.objects.filter(calendly_invitee_uri=invitee_uri).first()
        if not invitee:
            return JsonResponse({"status": "ignored", "reason": "invitee not found"})

        # Update the appointment status and invitee canceled flag.
        appointment = invitee.appointment
        if appointment:
            appointment.status = Appointments.Status.CANCELLED
            appointment.save()

        invitee.canceled = True
        invitee.save()

    return JsonResponse({"status": "ok"})


@superuser_required
def calendly_oauth_start(request):
    redirect_uri = request.build_absolute_uri(reverse("calendly_oauth_callback"))
    state = secrets.token_urlsafe(24)
    request.session["calendly_oauth_state"] = state

    from .calendly import build_oauth_authorize_url

    return redirect(build_oauth_authorize_url(redirect_uri=redirect_uri, state=state))


@superuser_required
def calendly_oauth_callback(request):

    expected_state = request.session.get("calendly_oauth_state")
    state = request.GET.get("state")
    if expected_state and state != expected_state:
        messages.error(request, "Calendly OAuth state mismatch.")
        return redirect("admin_appointments")

    code = request.GET.get("code")
    if not code:
        messages.error(request, "Missing Calendly OAuth code.")
        return redirect("admin_appointments")

    redirect_uri = request.build_absolute_uri(reverse("calendly_oauth_callback"))
    try:
        from .calendly import exchange_code_for_token, upsert_oauth_token

        token_data = exchange_code_for_token(code=code, redirect_uri=redirect_uri)
        upsert_oauth_token(token_data)
        messages.success(request, "Calendly connected (token stored).")
    except Exception:
        messages.error(request, "Calendly OAuth failed. Check server logs.")

    return redirect("admin_appointments")
