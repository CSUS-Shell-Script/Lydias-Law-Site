# forms.py holds the form classes for data input

from django import forms
from django.forms import modelformset_factory
from sitecontent.models import WebsiteContent, FAQItem, PracticeAreaItem


class WebsiteContentForm(forms.ModelForm):
    """
    Form for editing website content in the admin editor.
    CKEditor5 widgets are provided automatically by the CKEditor5Field on the model.
    Regina is my goat, the ckeditor version i was using was SO MUCH MORE WORK
    """

    class Meta:
        model = WebsiteContent
        fields = [
            # home Page
            'frontPageHeader',
            'frontPageDescription',
            # about Page
            'nameTitle',
            'aboutMeDescription',
            # contact Page
            'officeLocation',
            'phoneNumber',
            'emailAddress',
            # footer
            'footerDescription',
        ]
        widgets = {
            # CharFields - plain text inputs (CKEditor5 fields get their widget from the model)
            'frontPageHeader': forms.TextInput(attrs={
                'class': 'form-control',
                'maxlength': '140',
                'placeholder': 'Enter homepage header text'
            }),
            'nameTitle': forms.TextInput(attrs={
                'class': 'form-control',
                'maxlength': '120',
                'placeholder': 'Enter name/title'
            }),
            'officeLocation': forms.TextInput(attrs={
                'class': 'form-control',
                'maxlength': '200',
                'placeholder': 'Enter office address'
            }),
            'phoneNumber': forms.TextInput(attrs={
                'class': 'form-control',
                'maxlength': '20',
                'placeholder': 'e.g. (555) 555-5555'
            }),
            'emailAddress': forms.TextInput(attrs={
                'class': 'form-control',
                'maxlength': '254',
                'placeholder': 'Enter email address'
            }),
        }
        labels = {
            'frontPageHeader': 'Homepage Header',
            'frontPageDescription': 'Homepage Description',
            'nameTitle': 'Name/Title',
            'aboutMeDescription': 'About Me Description',
            'officeLocation': 'Office Location',
            'phoneNumber': 'Phone Number',
            'emailAddress': 'Email Address',
            'footerDescription': 'Footer Description',
        }
        help_texts = {
            'frontPageHeader': 'Displayed as the main headline on the homepage (max 140 characters)',
            'frontPageDescription': 'Displayed in the green banner below the hero image',
            'officeLocation': 'Address displayed on the Contact page (max 200 characters)',
            'phoneNumber': 'Phone number displayed on the Contact page (max 20 characters)',
            'emailAddress': 'Email address displayed on the Contact page',
            'footerDescription': 'Displayed in the website footer across all pages',
        }


class FAQItemForm(forms.ModelForm):
    class Meta:
        model = FAQItem
        fields = ["question", "answer", "display_order", "is_active"]
        widgets = {
            "question": forms.TextInput(
                attrs={"class": "form-control", "maxlength": "255", "placeholder": "Enter FAQ question"}
            ),
            "display_order": forms.NumberInput(
                attrs={"class": "form-control", "min": "0", "placeholder": "Display order"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["question"].required = False
        self.fields["answer"].required = False
        self.fields["display_order"].required = False
        self.fields["is_active"].required = False


class BaseFAQFormSet(forms.BaseModelFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        for form in self.forms:
            cleaned = getattr(form, "cleaned_data", None)
            if not cleaned:
                continue
            if cleaned.get("DELETE"):
                continue

            question = (cleaned.get("question") or "").strip()
            answer = (cleaned.get("answer") or "").strip()
            has_content = bool(question or answer)

            if not has_content:
                # Empty rows are allowed for unused extra forms.
                continue

            if not question:
                form.add_error("question", "Question is required when an answer is provided.")
            if not answer:
                form.add_error("answer", "Answer is required when a question is provided.")

            order = cleaned.get("display_order")
            if order is not None and order < 0:
                form.add_error("display_order", "Display order cannot be negative.")


FAQFormSet = modelformset_factory(
    FAQItem,
    form=FAQItemForm,
    formset=BaseFAQFormSet,
    can_delete=True,
    extra=0,
)


class PracticeAreaItemForm(forms.ModelForm):
    class Meta:
        model = PracticeAreaItem
        fields = ["title", "description", "is_active"]
        widgets = {
            "title": forms.TextInput(
                attrs={"class": "form-control", "maxlength": "255", "placeholder": "Enter practice area title"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].required = False
        self.fields["description"].required = False
        self.fields["is_active"].required = False


class BasePracticeAreaFormSet(forms.BaseModelFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        for form in self.forms:
            cleaned = getattr(form, "cleaned_data", None)
            if not cleaned:
                continue
            if cleaned.get("DELETE"):
                continue

            title = (cleaned.get("title") or "").strip()
            description = (cleaned.get("description") or "").strip()
            has_content = bool(title or description)

            if not has_content:
                continue

            if not title:
                form.add_error("title", "Title is required when a description is provided.")
            if not description:
                form.add_error("description", "Description is required when a title is provided.")


PracticeAreaFormSet = modelformset_factory(
    PracticeAreaItem,
    form=PracticeAreaItemForm,
    formset=BasePracticeAreaFormSet,
    can_delete=True,
    extra=0,
)
