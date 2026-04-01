from django.urls import path
from . import views
from .views import client_dashboard

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("signuppage/", views.signup_page, name="signuppage"),
    path("signup/", views.signup, name="signup"),
    path("confirmation-page/", views.confirmation_page, name="confirmation_page"),
    path("client/dashboard", client_dashboard, name="client_dashboard"),
    path("test-500/", views.trigger_500), 
 #   path('dashboard/', views.client_dashboard, name='client_dashboard'),

]
