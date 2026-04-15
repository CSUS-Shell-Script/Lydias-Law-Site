from django.db import models
from django_ckeditor_5.fields import CKEditor5Field

class WebsiteContent(models.Model):
    versionNumber = models.AutoField(primary_key=True)
    frontPageHeader = models.CharField(max_length=140, blank=True)
    frontPageDescription = CKEditor5Field(blank=True, config_name='default')

    nameTitle = models.CharField(max_length=120, blank=True)
    aboutMeDescription = CKEditor5Field(blank=True, config_name='default') 
    officeLocation = models.CharField(max_length=200, blank=True)
    phoneNumber = models.CharField(max_length=20, blank=True)
    emailAddress = models.CharField(max_length=254, blank=True)

    footerDescription = CKEditor5Field(blank=True, config_name='default')

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
         return f"Website content version {self.versionNumber}"


class FAQItem(models.Model):
    question = models.CharField(max_length=255, blank=True)
    answer = CKEditor5Field(blank=True, config_name='default')
    display_order = models.PositiveIntegerField(default=0, db_index=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        return self.question or f"FAQ #{self.pk}"


class PracticeAreaItem(models.Model):
    title = models.CharField(max_length=255, blank=True)
    description = CKEditor5Field(blank=True, config_name='default')
    display_order = models.PositiveIntegerField(default=0, db_index=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        return self.title or f"Practice Area #{self.pk}"
