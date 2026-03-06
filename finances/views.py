from datetime import datetime
import json
import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib import messages
#from users.views import is_admin_user
from core.decorators import superuser_required

import stripe
from users.models import User
from .models import Invoice, StripeWebhookEvent

stripe.api_key = settings.STRIPE_SECRET_KEY

# Standard Django logger for recording webhook activity.
logger = logging.getLogger(__name__)


def get_or_create_stripe_customer_id(user):
    # locks the user's row to prevent duplicate stripe customers for one user
    with transaction.atomic():
        user = type(user).objects.select_for_update().get(pk=user.pk)

    # check if client has stripe customer id
    if user.provider_customer_id:
        return user.provider_customer_id

    # create Stripe customer id if it doesn't exist
    customer = stripe.Customer.create(
        email=user.email,
        name=f"{user.first_name} {user.last_name}",
        metadata={"user_id": str(user.id)},
    )

    # save Stripe customer id
    user.provider_customer_id = customer.id
    user.save()

    return customer.id

@csrf_exempt
def stripe_webhook(request):
    """
    Stripe sends server-to-server webhook events to this endpoint.
    We verify the Stripe signature, de-duplicate events, and update
    invoice status based on the event type.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    # The shared secret from Stripe's dashboard, used to verify the signature.
    webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
    if not webhook_secret:
        logger.error("Stripe webhook secret not configured.")
        return JsonResponse({"error": "Webhook not configured"}, status=500)

    # Stripe requires the raw request body for signature verification.
    payload = request.body
    sig_header = request.headers.get("Stripe-Signature")
    if not sig_header:
        logger.warning("Missing Stripe-Signature header.")
        return JsonResponse({"error": "Missing signature"}, status=400)

    try:
        stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError:
        logger.warning("Invalid Stripe webhook payload.")
        return JsonResponse({"error": "Invalid payload"}, status=400)
    except stripe.error.SignatureVerificationError:
        logger.warning("Invalid Stripe webhook signature.")
        return JsonResponse({"error": "Invalid signature"}, status=400)

    # Store the raw JSON payload (signature already verified above).
    event_data = json.loads(payload.decode("utf-8"))
    event_id = event_data.get("id")
    if not event_id:
        logger.warning("Stripe webhook missing event id.")
        return JsonResponse({"error": "Missing event id"}, status=400)

    try:
        with transaction.atomic():
            # Store the event so duplicates can be detected safely.
            webhook_event, created = StripeWebhookEvent.objects.get_or_create(
                event_id=event_id,
                defaults={
                    "event_type": event_data.get("type", ""),
                    "payload": event_data,
                },
            )
    except IntegrityError:
        created = False
        webhook_event = None

    if not created:
        logger.info(
            "Duplicate Stripe event received: %s",
            event_id,
        )
        return JsonResponse({"status": "duplicate"}, status=200)

    event_type = event_data.get("type")
    invoice_obj = event_data.get("data", {}).get("object", {})

    if event_type in {"invoice.paid", "invoice.payment_failed", "invoice.voided"}:
        # Stripe invoice metadata can include our local invoice ID.
        metadata = invoice_obj.get("metadata") or {}
        local_invoice_id = metadata.get("local_invoice_id") or metadata.get("invoice_id")
        stripe_invoice_id = invoice_obj.get("id")

        invoice = None
        # Prefer a direct local ID lookup when available.
        if local_invoice_id:
            invoice = Invoice.objects.filter(id=local_invoice_id).first()
        # Fall back to the Stripe invoice ID if stored in our database.
        if not invoice and stripe_invoice_id:
            invoice = Invoice.objects.filter(stripe_invoice_id=stripe_invoice_id).first()

        if not invoice:
            logger.warning(
                "Stripe invoice event received but no matching invoice found. "
                "event_id=%s stripe_invoice_id=%s local_invoice_id=%s",
                event_id,
                stripe_invoice_id,
                local_invoice_id,
            )
            return JsonResponse({"status": "ignored"}, status=200)

        if event_type == "invoice.paid":
            # Paid means the invoice is complete.
            invoice.status = Invoice.Status.PAID
            invoice.paid = True
        elif event_type == "invoice.payment_failed":
            # Payment failed means the invoice is still unpaid.
            invoice.status = Invoice.Status.PAYMENT_FAILED
            invoice.paid = False
        elif event_type == "invoice.voided":
            invoice.status = Invoice.Status.VOIDED
            invoice.paid = False

        invoice.save(update_fields=["status", "paid"])
        logger.info(
            "Stripe invoice updated. invoice_id=%s status=%s event_id=%s",
            invoice.id,
            invoice.status,
            event_id,
        )

    logger.info(
        "Stripe webhook processed. event_id=%s type=%s",
        event_id,
        event_type,
    )
    return JsonResponse({"status": "success"}, status=200)

def create_invoice_items(stripe_customer_id, descriptions, quantities, unit_prices):
    # Creates an invoice item object for each unique line item.
    # Quanitity and unit_price are taken into consideration, total amount
    # is calculated during the creation of the stripe invoice.
    for desc, quantity, price in zip(descriptions, quantities, unit_prices):
        try:
            price_cents = int(float(price) * 100)
            quantity = int(quantity)
            
            # Validate that price and quantity are positive
            if price_cents <= 0:
                return JsonResponse({"success": False, "error": "Unit price must be greater than zero."})
            if quantity <= 0:
                return JsonResponse({"success": False, "error": "Quantity must be greater than zero."})

            stripe.InvoiceItem.create(
                unit_amount_decimal=price_cents,
                quantity=quantity,
                currency="usd", # Assuming only accepting usd.
                customer=stripe_customer_id,
                description=desc,
            )
        except ValueError:
            return JsonResponse({"success": False, "error": "Invalid quantity or price."})

def create_invoice(request):
    if request.method == "POST":
        # Customer Information.
        user_email = request.POST.get("email")
        # Invoice Details.
        issue_date = request.POST.get("issue_date")
        due_date = request.POST.get("due_date")
        customer_notes = request.POST.get("customer_notes")
        # List Items Information.
        descriptions = request.POST.getlist("description[]")
        quantities = request.POST.getlist("quantity[]")
        unit_prices = request.POST.getlist("unit_price[]")

        try:
            # Get user.
            user = User.objects.get(email=user_email)

            # Check if user has existing Stripe ID.
            stripe_customer_id = get_or_create_stripe_customer_id(user)

            # Create invoice items based on line items.
            result = create_invoice_items(stripe_customer_id, descriptions, quantities, unit_prices)
            # If create_invoice_items catches an exception, it returns a jsonResponse.
            # Handle that here and return it if an error occurs, otherwise result will be None.
            if isinstance(result, JsonResponse):
                return result

            try:
                issue_date_parsed = datetime.strptime(issue_date, "%Y-%m-%d")
                due_date_parsed = datetime.strptime(due_date, "%Y-%m-%d")
                if due_date_parsed < issue_date_parsed:
                    return JsonResponse({"success": False, "error": "Invalid due date, please set due date to be after the issue date."})
            except ValueError:
                return JsonResponse({"success": False, "error": "Date format error."})
            
            # Sets due date as a datetime object.
            # Stripe requires this to be a UNIX timestamp integer, so.. ya.
            due_date_timestamp = int(datetime.strptime(due_date, "%Y-%m-%d").timestamp())

            # Actually creates the overall stripe invoice object.
            stripe_invoice = stripe.Invoice.create(
                customer=stripe_customer_id,
                collection_method = "send_invoice",
                # Auto advance automatically finalizes the invoice.
                # This may need to change if we want to add another layer of confirmation
                # before charging users, if Lydia wants this feature.
                auto_advance=False,
                due_date=due_date_timestamp,
                pending_invoice_items_behavior="include", # Pulls all pending invoice items into invoice.
            )

            '''
            Webhook isn't working for finalize_invoice event type,
            so this is being done manually right now.
            '''

            stripe_invoice = stripe.Invoice.finalize_invoice(stripe_invoice.id)

            # Creates and saves new invoice DB object for created stripe invoice.
            Invoice.objects.create(
                user=user,
                amount=stripe_invoice.amount_due,
                stripe_invoice_id=stripe_invoice.id,
                hosted_invoice_url=stripe_invoice.hosted_invoice_url,
                status=Invoice.Status.PENDING,  # Defaults to pending, webhook handles changes.
            )

            return JsonResponse(
                {
                    "success": True,
                    "redirect_url": "/administrator/invoice_confirmation/",
                    "hosted_invoice_url": stripe_invoice.hosted_invoice_url,
                    "stripe_invoice_id": stripe_invoice.id,
                    
                }
            )

        except User.DoesNotExist:
            return JsonResponse({"success": False, "error": "User does not exist within the database, invoice has not been created."})
        except Exception as e:
            return JsonResponse({"success": False, "error": f"An error has occurred: {str(e)}. Please double check all fields are valid."})

    return render(request, "admin/create_invoice.html")

def invoice_confirmation(request):
    return render(request, "admin/invoice_confirmation.html")

# Retrieve strip invoice
def stripe_get_invoice(stripe_invoice_id: str):
    return stripe.Invoice.retrieve(stripe_invoice_id)

# List Client Invoices
def stripe_list_client_invoices(user, limit=50):
    return stripe.Invoice.list(customer=user.provider_customer_id, limit=limit)

@superuser_required # Ensures only visible to admins (PermissionDenied if not)
def admin_transactions(request):    
    # Fetch from local DB so we can link to Django users
    # Use select_related to get the user email in one database hit
    invoices = Invoice.objects.select_related("user").all().order_by("-created_at")

   # helper attributes so template logic works
    for inv in invoices:
        # Convert cents (stripe) to dollars for UI
        inv.amount_dollars = inv.amount / 100.0 if inv.amount else 0.0
        # Ensure status is uppercase for templates checks
        inv.display_status = str(inv.status).upper()    
    return render(request, "admin/transactions.html", {"invoices": invoices })

@superuser_required
def admin_stripe_invoice_detail(request, stripe_invoice_id):
    """
    Admin-only: Retrieve a Stripe invoice by stripe invoice ID
    Sends invoice info to frontend as JSON
    """
    try: 
        inv = stripe_get_invoice(stripe_invoice_id)
    except stripe.error.StripeError as e:
        return JsonResponse({"error": "Stripe error", "message": str(e)}, status=502)

    return JsonResponse({
        "id": inv.get("id"),
        "status": inv.get("status"),
        "amount_due": inv.get("amount_due"),    #cents
        "amount_paid": inv.get("amount_paid"),  #cents
        "currency": inv.get("currency"),
        "hosted_invoice_url": inv.get("hosted_invoice_url"),
        "invoice_pdf": inv.get("invoice_pdf"),
        "created": inv.get("created"),   #unix timestamp
        "customer": inv.get("customer"),
    })

@superuser_required
def admin_stripe_invoices_for_user(request, user_id):
    """
    Admin-only: Retrieve all stripe invoices for a local user id
    Uses user's stripe customer id -> provider_customer_id
    Sends invoice list to frontend as JSON
    """
    try: 
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return JsonResponse({"error": "User not found"}, status=404)
    
    if not user.provider_customer_id:
        return JsonResponse({"error": "User has no Stripe customer ID"}, status=400)
    
    try:
        res = stripe.Invoice.list(customer=user.provider_customer_id, limit=50)
    except stripe.error.StripeError as e:
        return JsonResponse({"error": "Stripe error", "message": str(e)}, status=502)

    invoices = []
    for inv in res.get("data", []):
        invoices.append({
             "id": inv.get("id"),
            "status": inv.get("status"),
            "amount_due": inv.get("amount_due"),   
            "amount_paid": inv.get("amount_paid"),  
            "currency": inv.get("currency"),
            "hosted_invoice_url": inv.get("hosted_invoice_url"),
            "invoice_pdf": inv.get("invoice_pdf"),
            "created": inv.get("created"),   
        })

    return JsonResponse({
        "user_id": user_id,
        "stripe_customer_id": user.provider_customer_id,
        "count": len(invoices),
        "invoices": invoices,
    })

@superuser_required
def void_invoice(request, stripe_invoice_id):
    """
    Admin-only: void an open Stripe invoice and update the local DB.
    Only PENDING invoices can be voided; PAID invoices cannot.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        invoice = Invoice.objects.get(stripe_invoice_id=stripe_invoice_id)
    except Invoice.DoesNotExist:
        return JsonResponse({"error": "Invoice not found"}, status=404)

    if invoice.status == Invoice.Status.VOIDED:
        return JsonResponse({"error": "Invoice is already voided"}, status=400)
    if invoice.status == Invoice.Status.PAID:
        return JsonResponse({"error": "Cannot void a paid invoice"}, status=400)

    try:
        stripe.Invoice.void_invoice(stripe_invoice_id)
    except stripe.error.StripeError as e:
        return JsonResponse({"error": "Stripe error", "message": str(e)}, status=502)

    invoice.status = Invoice.Status.VOIDED
    invoice.save(update_fields=["status"])

    logger.info(
        "Invoice voided. invoice_id=%s stripe_invoice_id=%s admin=%s",
        invoice.id,
        stripe_invoice_id,
        request.user.email,
    )
    return JsonResponse({"status": "voided"})


def create_checkout_session(request, invoice_id):
    try:
        invoice = Invoice.objects.get(id=invoice_id)
    except Invoice.DoesNotExist:
        return JsonResponse({"error": "Invoice not found"}, status=404)

    if invoice.status == Invoice.Status.PAID or invoice.paid:
        return JsonResponse({"error": "Invoice already paid"}, status=400)

    session = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": f"Invoice #{invoice.id}",
                },
                "unit_amount": invoice.amount,
            },
            "quantity": 1,
        }],
        metadata={"invoice_id": str(invoice.id)},
        success_url="http://localhost:8000/payment/success/",
		cancel_url="http://localhost:8000/dashboard/",
	)

    return redirect(session.url)
