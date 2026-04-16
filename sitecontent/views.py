from django.shortcuts import render
from .models import WebsiteContent, FAQItem, PracticeAreaItem
from django.contrib.auth import get_user_model
from django.http import HttpResponseServerError
from django.conf import settings

# Increment when you add more practice_area_N.png images to core/static/images.
# Must always equal the total number of practice area images available.
MAX_PA_IMAGES = 9

def _annotate_pa_images(queryset):
    items = list(queryset)
    for i, area in enumerate(items):
        area.image_static_path = f"images/practice_area_{min(i + 1, MAX_PA_IMAGES)}.png"
    return items


# Create your views here.

def get_latest_website_content():
    return WebsiteContent.objects.order_by("-versionNumber").first()

# Home Page request
def home(request):
    try:
        # Attempt to get the latest content
        content = get_latest_website_content()

        if not content:
            # Fallback if no content exists
            content = WebsiteContent(
                frontPageHeader="No Content Available",
                frontPageDescription="No description available."
            )

        role = request.GET.get("role", "guest") # Check URLs in core.
        faqs = FAQItem.objects.filter(is_active=True).order_by("display_order", "id")
        practice_areas = _annotate_pa_images(PracticeAreaItem.objects.filter(is_active=True))

        # Home page buttons: 1 minimum, 5 maximum
        from types import SimpleNamespace
        pa_buttons = practice_areas[:5] if practice_areas else [
            SimpleNamespace(image_static_path="images/practice_area_1.png", title="Practice Areas")
        ]

        # Render the normal about page
        return render(request, 'home.html', {
            "role": role,
            "BUILDING_ADDRESS": settings.BUILDING_ADDRESS,
            "GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY,
            'content': content,
            "faqs": faqs,
            "practice_areas": practice_areas,
            "pa_buttons": pa_buttons,
        })

    except Exception as e:
        # Log the error
        print(f"ERROR in about view: {e}")

        # Error page
        return HttpResponseServerError("An error occurred while loading the Home page.")


# About Page Request
def about(request, client=False):
    try:
        # Attempt to get the latest content from the WebsiteContent table
        content = get_latest_website_content()

        # Fallback if no content exists
        if not content:
            
            content = WebsiteContent(
                nameTitle = "No Content Available",
                aboutMeDescription = "No description available."
            )
        
        # Fallback if no title exists
        if content and not content.nameTitle:
            content.nameTitle = "No Content Availabe"

        # Fallback if no phone number exists
        if content and not content.aboutMeDescription:
            content.aboutMeDescription = "No Content Available"

        # Check which page to render
        page = 'about.html'
        if client:
            page = 'client/about.html'

        # Render the about page
        return render(request, page, {'content': content})

    except Exception as e:
        # Log the error
        print(f"ERROR in about view: {e}")

        # Error page
        return HttpResponseServerError("An error occurred while loading the About page.")
    

# Contact Page request
def contact(request, client=False):
    try:
        # Attempt to get the latest content from WebsiteContent table
        location = WebsiteContent.objects.order_by('-versionNumber').first()

        # Fallback if no content record exists yet
        if not location:
            location = WebsiteContent(
                officeLocation="No Content Available",
                phoneNumber="No Content Available",
                emailAddress="No Content Available",
            )
        else:
            if not location.officeLocation:
                location.officeLocation = "No Content Available"
            if not location.phoneNumber:
                location.phoneNumber = "No Content Available"
            if not location.emailAddress:
                location.emailAddress = "No Content Available"

        # Check which page to render
        page = 'contact.html'
        if client:
            page = 'client/contact.html'

        # Render contact page
        return render(request, page, {
            'location': location,
            "BUILDING_ADDRESS": settings.BUILDING_ADDRESS,
            "GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY,
            'content': location,
        })
    
    except Exception as e:
        # Log the error
        print(f"ERROR in about view: {e}")

        # Error page
        return HttpResponseServerError("An error occurred while loading the Contact page.")


