from django.shortcuts import render
from .models import WebsiteContent, FAQItem
from django.contrib.auth import get_user_model
from django.http import HttpResponseServerError
from django.conf import settings


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

        # Render the normal about page
        return render(request, 'home.html', {
            "role": role,
            "GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY,            
            'content': content,
            "faqs": faqs,
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
        User = get_user_model()

        # Attempt to get the latest content from WebsiteContent table
        location = WebsiteContent.objects.order_by('-versionNumber').first()

        # Attempts to get Lydia's information from User table
        lydia = User.objects.filter(role=User.Role.ADMIN).first()

        # Fallback if no location exists
        if not location:
            location = WebsiteContent(
                officeLocation="No Content Available"
            )

        # Fallback if no email exists
        if lydia and not lydia.email:
            lydia.email = "No Content Available"

        # Fallback if no phone number exists
        if lydia and not lydia.phone_number:
            lydia.phone_number = "No Content Available"

        # Check which page to render
        page = 'contact.html'
        if client:
            page = 'client/contact.html'
        content = location

        # Render contact page
        return render(request, page, {
            'location': location,
            'lydia': lydia,
            "GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY,
            'content': content,            
        })
    
    except Exception as e:
        # Log the error
        print(f"ERROR in about view: {e}")

        # Error page
        return HttpResponseServerError("An error occurred while loading the Contact page.")


