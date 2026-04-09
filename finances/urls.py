from django.urls import path

from . import views

urlpatterns = [
    # Stripe webhook endpoint (server-to-server callbacks).
    path("webhooks/stripe/", views.stripe_webhook, name="stripe_webhook"),
    path("api/admin/stripe/invoice/<str:stripe_invoice_id>/", views.admin_stripe_invoice_detail, name="admin_stripe_invoice_detail"),
    path("api/admin/stripe/invoice/<str:stripe_invoice_id>/void/", views.void_invoice, name="void_invoice"),
    path("api/admin/stripe/user/<int:user_id>/invoices/", views.admin_stripe_invoices_for_user, name="admin_stripe_invoices_for_user"),
    path("checkout/<str:invoice_id>", views.create_checkout_session, name="create_checkout_session"),
]
