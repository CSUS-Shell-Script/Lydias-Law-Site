# views.py is responsible for defining how the app ( this file, views.py, is in the app "core") interacts with users' requests like for data processing, rendering pages, responding to actions
# essentialy: user interactions -> tangible responses

from django.shortcuts import render, HttpResponse, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.core.paginator import Paginator
from allauth.account.utils import complete_signup
from allauth.account import app_settings as allauth_settings
from allauth.account.adapter import get_adapter
from allauth.account.models import EmailAddress, EmailConfirmation, get_emailconfirmation_model
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from sitecontent.models import WebsiteContent
from django.conf import settings
from finances.models import Invoice
from appointments.models import Appointments, Invitee
from users.views import is_admin_user
from django.utils import timezone


''' Are these needed anymore if site content is covering them?
    Home, About, and Contact are all being handled by site content views,
    making some of these and potentially more in the future obsolete.
'''
# Public views
def home(r):
    role = r.GET.get("role", "guest")
    return render(r, "home.html", {"role": role, "GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY})
  
# Is this method 
def practice_areas(r):
    content = WebsiteContent.objects.latest('created_at')
    return render(r, "practice_areas.html", {"content": content})

def about(r): return render(r, "about.html")
def services(r): return render(r, "services.html")
def contact(r): return render(r, "contact.html", {"GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY})
def payment(r): 
    if r.method == "POST":
        invoice_id = r.POST.get("invoice_id")
        return redirect("create_checkout_session", invoice_id=invoice_id)
    return render(r, "payment.html")
def schedule(r): return render(r, "schedule.html")
def privacy(r): return render(r, "privacy.html")
def appointment_confirmation(r): return render (r, "appointment_confirmation.html")
def payment_success(r): return render (r, "payment_success.html")

def login(r): 
    role = r.GET.get("role", "guest")
    return render(r, "users/login.html", {"role": role})

# admin views (login temporarily disabled for testing)
# @login_required
#def admin_dashboard(r): return render(r, "admin/dashboard.html")
# @login_required
def admin_schedule(r): return render(r, "admin/schedule.html")
# @login_required
def admin_clients(r): return render(r, "admin/clients.html")
# @login_required
def admin_editor(request):
    """
    Admin editor view for editing WebsiteContent.
    Fetches the latest content version and allows editing.
    """
    from .forms import WebsiteContentForm

    # get the latest WebsiteContent or create default if none exists
    content = WebsiteContent.objects.order_by('-versionNumber').first()

    if content is None:
        content = WebsiteContent.objects.create(
            frontPageHeader="Welcome",
            frontPageDescription="Default description"
        )

    if request.method == 'POST':
        form = WebsiteContentForm(request.POST, instance=content)
        if form.is_valid():
            form.save()
            messages.success(request, 'Website content updated successfully!')
            return redirect('admin_editor')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = WebsiteContentForm(instance=content)

    return render(request, "admin/editor.html", {
        'form': form,
        'content': content,
    })
# @login_required
def admin_history(r): return render(r, "admin/history.html")
# @login_required
def admin_appointment_confirmation(r): return render(r, "admin/appointment_confirmation.html")
# @login_required
def admin_create_invoices(r): return render(r, "admin/create_invoice.html")

@login_required
def admin_appointments(request):
    is_admin_user(request.user)

    qs = Appointments.objects.select_related('user_id').prefetch_related('invitees').all()

    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter and status_filter in Appointments.Status.values:
        qs = qs.filter(status=status_filter)

    # Filter by date range
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from:
        qs = qs.filter(start_time__date__gte=date_from)
    if date_to:
        qs = qs.filter(start_time__date__lte=date_to)

    paginator = Paginator(qs, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'admin/appointments.html', {
        'page_obj': page_obj,
        'status_choices': Appointments.Status.choices,
        'current_status': status_filter,
        'date_from': date_from,
        'date_to': date_to,
    })

@login_required
def admin_appointment_detail(request, pk):
    is_admin_user(request.user)

    appointment = get_object_or_404(
        Appointments.objects.select_related('user_id').prefetch_related('invitees'),
        pk=pk
    )

    return render(request, 'admin/appointment_detail.html', {
        'appointment': appointment,
        "status_choices": Appointments.Status.choices,
    })


@require_POST
@login_required
def admin_appointment_cancel(request, pk):
    is_admin_user(request.user)

    appointment = get_object_or_404(
        Appointments.objects.prefetch_related("invitees"),
        pk=pk,
    )

    if appointment.status not in (Appointments.Status.PENDING, Appointments.Status.CONFIRMED):
        messages.warning(request, "Only Pending or Confirmed appointments can be cancelled.")
        return redirect(request.POST.get("next") or reverse("admin_appointment_detail", args=[pk]))

    reason = (request.POST.get("reason") or "").strip()
    if not reason:
        messages.error(request, "Cancellation reason is required.")
        return redirect(request.POST.get("next") or reverse("admin_appointment_detail", args=[pk]))

    appointment.status = Appointments.Status.CANCELLED
    appointment.cancellation_reason = reason
    appointment.cancelled_at = timezone.now()
    appointment.save(update_fields=["status", "cancellation_reason", "cancelled_at"])

    # Mirror cancellation info onto invitees (if present)
    appointment.invitees.update(canceled=True, cancellation_reason=reason)

    # Best-effort Calendly cancellation (feature-flagged / offline-safe)
    if appointment.calendly_event_uri:
        try:
            from appointments.calendly import cancel_scheduled_event, calendly_api_enabled

            if not calendly_api_enabled():
                messages.info(
                    request,
                    "Calendly cancellation skipped (site not live yet — expected).",
                )
            else:
                ok = cancel_scheduled_event(
                    calendly_event_uri=appointment.calendly_event_uri,
                    cancellation_reason=reason,
                )
                if not ok:
                    messages.warning(
                        request,
                        "Appointment cancelled locally. Calendly cancellation failed (best effort).",
                    )
        except Exception:
            # Never block local cancellation on Calendly issues
            messages.warning(
                request,
                "Appointment cancelled locally. Calendly cancellation was skipped/failed (expected if site isn't live yet).",
            )

    messages.success(request, "Appointment cancelled.")
    return redirect(request.POST.get("next") or reverse("admin_appointment_detail", args=[pk]))


@require_POST
@login_required
def admin_appointment_update_status(request, pk):
    is_admin_user(request.user)

    appointment = get_object_or_404(Appointments.objects.prefetch_related("invitees"), pk=pk)
    next_url = request.POST.get("next") or reverse("admin_appointment_detail", args=[pk])

    new_status = (request.POST.get("status") or "").strip()
    valid_values = set(Appointments.Status.values)
    if new_status not in valid_values:
        messages.error(request, "Invalid status.")
        return redirect(next_url)

    if new_status == appointment.status:
        messages.info(request, "Status unchanged.")
        return redirect(next_url)

    if not Appointments.can_transition_status(appointment.status, new_status):
        messages.warning(request, "That status change isn’t allowed.")
        return redirect(next_url)

    if new_status == Appointments.Status.CANCELLED:
        reason = (request.POST.get("reason") or "").strip()
        if not reason:
            messages.error(request, "Cancellation reason is required.")
            return redirect(next_url)

        appointment.status = Appointments.Status.CANCELLED
        appointment.cancellation_reason = reason
        appointment.cancelled_at = timezone.now()
        appointment.save(update_fields=["status", "cancellation_reason", "cancelled_at"])
        appointment.invitees.update(canceled=True, cancellation_reason=reason)

        if appointment.calendly_event_uri:
            try:
                from appointments.calendly import cancel_scheduled_event, calendly_api_enabled

                if not calendly_api_enabled():
                    messages.info(
                        request,
                        "Calendly cancellation skipped (site not live yet — expected).",
                    )
                else:
                    ok = cancel_scheduled_event(
                        calendly_event_uri=appointment.calendly_event_uri,
                        cancellation_reason=reason,
                    )
                    if not ok:
                        messages.warning(
                            request,
                            "Appointment cancelled locally. Calendly cancellation failed (best effort).",
                        )
            except Exception:
                messages.warning(
                    request,
                    "Appointment cancelled locally. Calendly cancellation was skipped/failed (expected if site isn't live yet).",
                )

        messages.success(request, "Status updated to Cancelled.")
        return redirect(next_url)

    # Non-cancel transitions
    appointment.status = new_status
    appointment.save(update_fields=["status"])
    messages.success(request, "Status updated.")
    return redirect(next_url)

# Client Views
#@login_required
def client_about(r): return render(r, "client/about.html")


# Client account/profile view
@login_required
def client_account(request):
    if request.method == "POST":
        field = request.POST.get("field", "")
        user = request.user

        if field == "name":
            first_name = (request.POST.get("first_name") or "").strip()
            last_name = (request.POST.get("last_name") or "").strip()
            if not first_name or not last_name:
                messages.error(request, "First name and last name cannot be blank.")
            else:
                user.first_name = first_name
                user.last_name = last_name
                user.save(update_fields=["first_name", "last_name"])
                messages.success(request, "Name updated successfully.")

        elif field == "phone":
            import re
            raw_phone = (request.POST.get("new_value") or "").strip()
            if not raw_phone:
                messages.error(request, "Phone number cannot be blank.")
            elif not re.match(r"^\d{7,15}$", raw_phone):
                messages.error(request, "Phone number must be 7-15 digits (numbers only).")
            else:
                user.phone_number = raw_phone
                user.save(update_fields=["phone_number"])
                messages.success(request, "Phone number updated successfully.")

        else:
            messages.error(request, "That field cannot be updated here.")

        return redirect("client_account")

    context = get_user_account_data(request)
    return render(request, "client/account.html", context)

# Get feilds for client's account/profile view
def get_user_account_data(request):
    user = request.user # get user table

    # format the phone number for UI
    raw_phone = getattr(user, "phone_number", "")
    #removes characters in phone numer that aren't digits
    digits = ""
    for ch in str(raw_phone):
        if ch.isdigit():
            digits += ch

    if len(digits) == 10:
        phone = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    else:
        phone = str(raw_phone)  # fallback

    return {
        # will be "" if not present
        "email": user.email or "",
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "phone": phone or ""
    }

#@login_required
def client_contact(r): return render(r, "client/contact.html")
#@login_required
#def client_payment(r): return render(r, "client/payment.html")
#@login_required
def client_practice_areas(r):
    content = WebsiteContent.objects.latest('created_at')
    return render(r, "client/practice_areas.html", {"content": content})

#@login_required
def client_invoices(r): 
    user = r.user

   # Current invoice to pay (pending)
    current_invoice = Invoice.objects.filter(user=user, status=Invoice.Status.PENDING).order_by('created_at').first()
    
    # Convert amount to dollars for display
    if current_invoice:
        current_invoice.display_amount = current_invoice.amount / 100
        stripe_url = current_invoice.hosted_invoice_url
    else:
        stripe_url = None

    # Past invoices (paid or failed), newest first, limit 10
    past_invoices = Invoice.objects.filter(user=user)
    if current_invoice:
        past_invoices = past_invoices.exclude(id=current_invoice.id)
    past_invoices = past_invoices.order_by('-created_at')[:10]

    # Convert past invoice amounts to dollars
    for inv in past_invoices:
        inv.display_amount = inv.amount / 100

    return render(r, "client/invoices.html", {
        "current_invoice": current_invoice,
        "stripe_url": stripe_url,
        "past_invoices": past_invoices,
    })

#@login_required
def client_privacy(r):
    return render(r, "client/privacy.html")
#@login_required
def client_appointment_request_confirmation(r): return render(r, "client/appointment_request_confirmation.html")
#@login_required
def client_appointment_denied_confirmation(r): return render(r, "client/appointment_denied_confirmation.html")
#@login_required
def client_appointment_confirmation(r): return render(r, "client/appointment_confirmation.html")
