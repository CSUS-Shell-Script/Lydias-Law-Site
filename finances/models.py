from django.db import models
from django.conf import settings

class Payment(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments", db_index=True)
    amount = models.PositiveIntegerField(help_text="minor units (cents)")
    currency = models.CharField(max_length=3, default="USD")
    description = models.CharField(max_length=255, null=True, blank=True)
    
    class Status(models.TextChoices):
        SUCCESS = "SUCCESS", "Success"
        PENDING = "PENDING", "Pending"
        REFUNDED = "REFUNDED", "Refunded"
        FAILED = "FAILED", "Failed"

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    paid_at = models.DateTimeField(null=True, blank=True)

# Invoice Table
class Invoice(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(    # Foreign key to user who invoice belongs to
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="invoices",
        db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    amount = models.PositiveIntegerField(help_text="minor units (cents)")

    class Status(models.TextChoices):
        # Status values used by Stripe webhook updates.
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        PAYMENT_FAILED = "PAYMENT_FAILED", "Payment Failed"
        VOIDED = "VOIDED", "Voided"

    # Primary invoice state used throughout the app.
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    # Backwards-compatible flag for legacy code that checks paid/unpaid.
    paid = models.BooleanField(default=False)
    # Stripe's invoice ID so we can link webhooks to our invoices.
    stripe_invoice_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    # The customer-visible invoice number shown in Stripe (e.g. SODQXXCO-0002).
    stripe_invoice_number = models.CharField(max_length=255, null=True, blank=True)
    # Stripe's invoice URL to easily find this invoice in the future.
    hosted_invoice_url = models.URLField(max_length=500, null=True, blank=True)

    # Output Readability
    def __str__(self):
        return f"Invoice #{self.id} - User {self.user.id} - ${self.amount}"
    
    class Meta:
        db_table = "invoices"
        ordering = ["-created_at"]
    
    # To get and show client's name on transaction page for admin
    # If name is not listed, email is shown, if no email -> unknown
    @property
    def client_name(self):
        if self.user and (self.user.first_name or self.user.last_name):
            return f"{self.user.first_name} {self.user.last_name}"
        return self.user.email if self.user else "Unknown"


class StripeWebhookEvent(models.Model):
    """
    Records Stripe webhook events for idempotency and debugging.
    Stripe retries events, so we must detect duplicates.
    """
    id = models.BigAutoField(primary_key=True)
    # Stripe's event ID is unique across all events.
    event_id = models.CharField(max_length=255, unique=True, db_index=True)
    event_type = models.CharField(max_length=100)
    received_at = models.DateTimeField(auto_now_add=True)
    # Full payload for troubleshooting and audits.
    payload = models.JSONField()

    class Meta:
        db_table = "stripe_webhook_events"
        ordering = ["-received_at"]