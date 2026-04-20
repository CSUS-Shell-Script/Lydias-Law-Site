"""
URL configuration for Lydias_Law_Site project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from django.contrib.staticfiles.storage import staticfiles_storage
from django.contrib.sitemaps.views import sitemap
from core.sitemaps import StaticViewSitemap

sitemaps = {
    'static': StaticViewSitemap(),
}

urlpatterns = [
    path('admin/', admin.site.urls),
    path("", include(('users.urls', 'users'), namespace='users')),
    path("", include("core.urls")),
    path("accounts/", include("allauth.urls")),
    path("appointments/", include("appointments.urls")),
    path("ckeditor5/", include('django_ckeditor_5.urls')),
    path("", include("finances.urls")),
    
    # For SEO (Google crawl)
    # From core/sitemap.py and core/static/core/robot.txt file
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    path("robots.txt", RedirectView.as_view(
        url=staticfiles_storage.url("core/robots.txt"),
        permanent=True
    )),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


