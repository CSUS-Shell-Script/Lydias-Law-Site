from django.shortcuts import render, HttpResponse, redirect
from allauth.account.models import EmailConfirmation, EmailConfirmationHMAC
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import get_user_model, login as auth_login, authenticate, logout
from allauth.account.utils import complete_signup
from allauth.account import app_settings as allauth_settings
from allauth.account.adapter import get_adapter
from allauth.account.models import EmailAddress, EmailConfirmation, get_emailconfirmation_model
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import Http404
from finances.models import Invoice
from django.db.models import Sum
from django.db.models.functions import Coalesce
from decimal import ROUND_HALF_UP, Decimal
from appointments.models import Appointments
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from sitecontent.views import get_latest_website_content
from .forms import UserSignUpForm


# Directs to login page
def login(r): 
    role = r.GET.get("role", "guest")
    return render(r, "users/login.html", {"role": role})

# Handles login form submission and authenticates user
@require_http_methods(["GET", "POST"])
def login_view(request):
    """
    Render login page (GET) and authenticate credentials (POST).
    Uses django.contrib.auth.authenticate() with email + password.
    """
    if request.method == "GET":
        role = request.GET.get("role", "guest")
        return render(request, "users/login.html", {"role": role})

    # POST
    email = (request.POST.get("email") or "").strip().lower()
    password = request.POST.get("password") or ""

    # authenticate() will look up by USERNAME_FIELD (email in our model)
    user = authenticate(request, email=email, password=password)

    if user is None:
        # Wrong email/password
        messages.error(request, "Invalid credentials.")
        return render(request, "users/login.html", {"role": request.GET.get("role", "guest")}, status=401)

    if not user.is_active:
        # Users have is_active=False until email is verified
        messages.error(request, "Please verify your email to activate your account.")
        return render(request, "users/login.html", {"role": request.GET.get("role", "guest")}, status=403)

    # Success: log them in and redirect
    auth_login(request, user)
    if user.is_staff == 1:
        return redirect("admin_dashboard")
    return redirect("client_dashboard")

def signup_page(r):
    return render(r, "users/signup.html")

# We should start to think about refactoring the views into separated views files and import them into this main views file.
# Signup view, directs to signup page and handles signup form submission
def signup(r):
    User = get_user_model()
    if r.method == 'POST':
        first_name = (r.POST.get('first-name') or "").strip()
        last_name = (r.POST.get('last-name') or "").strip()
        email = (r.POST.get('email') or "").strip()
        phone_number = (r.POST.get('phone-number') or "").strip()

        password1 = r.POST.get('password1') or ""
        password2 = r.POST.get('password2') or ""

        if (first_name == "" or 
            last_name == "" or 
            email == "" or 
            phone_number == "" or 
            password1 == "" or 
            password2 == ""):
            messages.error(r, "All fields must be filled in")
            return render(r, "users/signup.html")

        # Basic checks
        if password1 != password2:
            messages.error(r, "Passwords do not match.")
            return render(r, 'users/signup.html')

        if password1 != password1.strip():
            messages.error(r, "Password cannot start or end with spaces.")
            return render(r, 'users/signup.html')

        if User.objects.filter(email__iexact=email).exists():
            messages.error(r, "An account with that email already exists.")
            return render(r, 'users/signup.html')

        # Create the user with a **real** password
        user = User.objects.create_user(
            email=email,
            password=password1,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            role=User.Role.CLIENT # Change new user to client role.
        )

        # Create Email Address Object.
        email_address = EmailAddress.objects.create(
            user=user,
            email=user.email,
            primary=True,
            verified=False
        )

        # Create Email Confirmation using the model configured by allauth
        # (HMAC vs DB-backed). This ensures the generated key matches what
        # the confirmation view expects when validating the link.
        model = get_emailconfirmation_model()
        email_confirmation = model.create(email_address)
        # Only call save() if the returned object is a DB model instance
        # (HMAC-based confirmations won't have a save method).
        if hasattr(email_confirmation, "save"):
            email_confirmation.save()

        # Send Email Confirmation.
        email_confirmation.send(request=r, signup=True)

        return complete_signup(
            r,
            user,
            allauth_settings.EMAIL_VERIFICATION,
            success_url=reverse('client_dashboard')
        )
    
# Logout view
@login_required
def logout_view(r):
    logout(r) # removes user's session data / token 
    messages.success(r, "You have been logged out.")
    return redirect('home')

# Email verification notice view
def email_verification_notice(r):
    return render(r, 'users/confirmation-page.html')

# Email confirmation page view
def confirmation_page(r):
    return render(r, 'users/confirmation-page.html')

# Caclulate user balance helper function
def get_user_balance_dollars(user_id):
    """
    Calculates total unpaid invoice amount for the given user.
    Converts from cents to dollars and rounds to 2 decimal places.
    """
    # get all unpaid invoices for this user
    total_cents = (
        # Any invoice that is not PAID counts toward the unpaid balance.
        Invoice.objects.filter(user_id=user_id)
        .exclude(status=Invoice.Status.PAID)
        .aggregate(total=Coalesce(Sum("amount"), 0))["total"]
    )

    # convert to dollars and round to 2 decimal places
    balance_dollars = (Decimal(total_cents) / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return balance_dollars

# Get next three appointments helper function
def get_next_three_appointments(user_id):
    """
    Return the next 3 upcoming (non-cancelled) appointments for this user,
    ordered soonest-first.
    """
    now = timezone.now()
    qs = (
        Appointments.objects
        .filter(user_id=user_id, start_time__gte=now)
        .exclude(status=Appointments.Status.CANCELLED)
        .order_by("start_time")
    )
    return list(qs[:3])

# Get next three appointments admin helper function
def admin_get_next_three_appointments(user=None):
    """
    Return the next 3 upcoming (non-cancelled) appointments.
    If a user is provided and is not an admin, only that user's
    appointments are returned. Admins see all upcoming appointments.
    """
    now = timezone.now()

    qs = Appointments.objects.filter(
        start_time__gte=now
    ).exclude(
        status=Appointments.Status.CANCELLED
    ).order_by("start_time")

    # If a user is passed and they’re not staff/superuser,
    # limit to their own appointments.
    if user and not (user.is_staff or user.is_superuser):
        qs = qs.filter(user_id=user.id)

    return list(qs[:5])


# Client dashboard view
@login_required
def client_dashboard(request):
    user = request.user
    content = get_latest_website_content()
    balance_dollars = get_user_balance_dollars(user.id)
    upcoming_appts = get_next_three_appointments(user.id)   
    return render(request, "client/dashboard.html", {
        "user": user,
        "balance_dollars": balance_dollars,
        "upcoming_appts": upcoming_appts,
        "content": content,
    })

# Helper: only allow staff/admin users
def is_admin_user(user):
    if not user.is_authenticated or not user.is_staff:
        raise PermissionDenied
    return user.is_authenticated and user.is_staff

# Admin dashboard view
@login_required
def admin_dashboard(r): 
    content = get_latest_website_content()
    upcoming_appts = admin_get_next_three_appointments(r.user)
    return render(r, "admin/dashboard.html", {
        "upcoming_appts": upcoming_appts,
        "content": content
    })


# Email confirmation redirection view
def instant_email_confirm_view(r, key):
    confirmation = EmailConfirmationHMAC.from_key(key)
    if not confirmation:
        try:
            confirmation = EmailConfirmation.objects.get(key=key.lower())
        except EmailConfirmation.DoesNotExist:
            raise Http404("Invalid confirmation key.")

    user = confirmation.email_address.user
    confirmation.confirm(r)

    auth_login(r, user)

    # Upon signing up, the user was not logging into the account that they had just created and authenticated.
    # This function fixes this issue by redirecting the user here to log in before going to the dashboard.
    return redirect(reverse('client_dashboard'))