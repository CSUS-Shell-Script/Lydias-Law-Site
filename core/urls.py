# urls.py maps URLs to views

from django.urls import path, include
from . import views
from sitecontent.views import about
from sitecontent.views import home
from sitecontent.views import contact
from users.views import logout_view as users_logout_view
from users.views import instant_email_confirm_view as email_confirm_view
from users.views import client_dashboard as users_client_dashboard
from users.views import admin_dashboard as users_admin_dashboard
from finances.views import create_invoice as finances_create_invoice
from finances.views import invoice_confirmation as finances_invoice_confirmation
from finances import views as finance_views

''' IMPORTANT FOR ALL WHO READ '''
# There seems to be a potential conflicts with different views that have been made for the same pages.
# For example there was a contact view in the sitecontent app but also one here in the core app.
# We should take time to separate views and organize/clean them up at some point.
''' IMPORTANT FOR ALL WHO READ '''

urlpatterns = [
    ########## Public pages ##########
    path("", home, name="home"),
    path("practice-areas/", views.practice_areas, name="practice_areas"),
    path("about/", about, name="about"),
    path("services/", views.services, name="services"),
    path("contact/", contact, name="contact"),
    path("payment/", views.payment, name="payment"),
    path("schedule/", views.schedule, name="schedule"),
    path("privacy/", views.privacy, name="privacy"),
    path("appointment_confirmation/", views.appointment_confirmation, name="appointment_confirmation"),
    path("payment/success/", views.payment_success, name="payment_success"),
    path("payment/failure/", views.payment_failure, name="payment_failure"),

    ########## Users pages ##########
    path("users/", include("users.urls")),
    # path("login/", users.views.login, name="login"),
    # path("signup/", views.signup, name="signup"),
    # path("accounts/", include("allauth.urls")),
    # path('verify/', views.confirmation_page, name='confirmation_page'),

    ########## Admin pages ##########
    # admin panel pages (using 'administrator' to avoid conflict with django "admin" keyword)
    path("administrator/", users_admin_dashboard, name="admin_dashboard"),
    path("administrator/dashboard/", users_admin_dashboard, name="admin_dashboard"),
    path("administrator/schedule/", views.admin_schedule, name="admin_schedule"),
    path("administrator/transactions/", finance_views.admin_transactions, name="admin_transactions"),
    path("administrator/clients/", views.admin_clients, name="admin_clients"),
    path("administrator/editor/", views.admin_editor, name="admin_editor"),
    path("administrator/history/", views.admin_history, name="admin_history"),
    path("administrator/appointments/", views.admin_appointments, name="admin_appointments"),
    path("administrator/appointments/<int:pk>/", views.admin_appointment_detail, name="admin_appointment_detail"),
    path("administrator/appointments/<int:pk>/cancel/", views.admin_appointment_cancel, name="admin_appointment_cancel"),
    path("administrator/appointments/<int:pk>/accept/", views.admin_appointment_accept, name="admin_appointment_accept"),
    path("administrator/appointments/<int:pk>/status/", views.admin_appointment_update_status, name="admin_appointment_update_status"),
    path("logout/", users_logout_view, name="logout"),
    path('accounts/confirm-email/<str:key>/', email_confirm_view, name='account_confirm_email'),
    path("administrator/appointment_confirmation/", views.admin_appointment_confirmation, name="admin_appointment_confirmation"),
    path("administrator/create_invoices/", finances_create_invoice, name="admin_create_invoices"),
    path("administrator/invoice_confirmation/", finances_invoice_confirmation, name="admin_invoice_confirmation"),

    ########### Client pages ###########
    # These have "view.<something" because we are calling it from core > views.py (needed for testing)
    path("client/about/", views.client_about, name="client_about"),
    path("client/account/", views.client_account, name="client_account"),
    path("client/contact/", views.client_contact, name="client_contact"),
    path("client/dashboard/", users_client_dashboard, name="client_dashboard"),
    path("client/practice-areas/", views.client_practice_areas, name="client_practice_areas"),
    path("client/invoices/", views.client_invoices, name="client_invoices"),
    path("client/privacy/", views.client_privacy, name="client_privacy"),
    path("client/appointment_confirmation/", views.client_appointment_confirmation, name="client_appointment_confirmation"),

    # I have these paths below commented out because when we implement authentication, users will be authenticated with the auth_views method

    #path("login/", auth_views.LoginView.as_view(template_name="login.html"), name="login"),
    # path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    # path("password-reset/", auth_views.PasswordResetView.as_view(), name="password_reset"),


]
