from django.test import TestCase, RequestFactory

from sitecontent.models import WebsiteContent
from sitecontent.context_processors import footer_content


############################### Website Content Model (LLW-288) ###############################

class WebsiteContentModelTests(TestCase):

    # Test: WebsiteContent can be created with all fields populated
    def test_create_with_all_fields(self):
        content = WebsiteContent.objects.create(
            frontPageHeader="Welcome Header",
            frontPageDescription="<p>Front page description</p>",
            stepParentAdoptionDescription="<p>Step-parent</p>",
            adultAdoptionDescription="<p>Adult</p>",
            guardianshipDescription="<p>Guardianship</p>",
            guardianshipToAdoptionDescription="<p>G to A</p>",
            independentAdoptionDescription="<p>Independent</p>",
            nameTitle="Lydia A. Suprun",
            aboutMeDescription="<p>About me</p>",
            officeLocation="123 Main St",
            footerDescription="<p>Footer text</p>",
        )
        content.refresh_from_db()
        self.assertEqual(content.frontPageHeader, "Welcome Header")
        self.assertEqual(content.frontPageDescription, "<p>Front page description</p>")
        self.assertEqual(content.nameTitle, "Lydia A. Suprun")
        self.assertEqual(content.aboutMeDescription, "<p>About me</p>")
        self.assertEqual(content.officeLocation, "123 Main St")
        self.assertEqual(content.footerDescription, "<p>Footer text</p>")
        self.assertEqual(content.stepParentAdoptionDescription, "<p>Step-parent</p>")
        self.assertEqual(content.adultAdoptionDescription, "<p>Adult</p>")
        self.assertEqual(content.guardianshipDescription, "<p>Guardianship</p>")
        self.assertEqual(content.guardianshipToAdoptionDescription, "<p>G to A</p>")
        self.assertEqual(content.independentAdoptionDescription, "<p>Independent</p>")

    # Test: versionNumber auto-increments for each new row
    def test_version_number_auto_increments(self):
        v1 = WebsiteContent.objects.create(frontPageHeader="Version 1")
        v2 = WebsiteContent.objects.create(frontPageHeader="Version 2")
        v3 = WebsiteContent.objects.create(frontPageHeader="Version 3")
        self.assertGreater(v2.versionNumber, v1.versionNumber)
        self.assertGreater(v3.versionNumber, v2.versionNumber)

    # Test: Latest version is retrieved by ordering on versionNumber descending
    def test_latest_version_retrieved_by_views(self):
        WebsiteContent.objects.create(frontPageHeader="Old")
        WebsiteContent.objects.create(frontPageHeader="Newer")
        latest = WebsiteContent.objects.create(frontPageHeader="Latest")

        fetched = WebsiteContent.objects.order_by('-versionNumber').first()
        self.assertEqual(fetched.pk, latest.pk)
        self.assertEqual(fetched.frontPageHeader, "Latest")

    # Test: __str__ returns expected format
    def test_str_representation(self):
        content = WebsiteContent.objects.create(frontPageHeader="Test")
        self.assertEqual(str(content), f"Website content version {content.versionNumber}")

    # Test: created_at and updated_at are set automatically
    def test_timestamps_auto_set(self):
        content = WebsiteContent.objects.create(frontPageHeader="Timestamps")
        self.assertIsNotNone(content.created_at)
        self.assertIsNotNone(content.updated_at)


############################### Footer Context Processor (LLW-288) ###############################

class FooterContextProcessorTests(TestCase):

    def setUp(self):
        self.factory = RequestFactory()

    # Test: Context processor returns content when WebsiteContent exists
    def test_returns_content(self):
        WebsiteContent.objects.create(footerDescription="<p>Footer here</p>")
        request = self.factory.get('/')
        ctx = footer_content(request)
        self.assertIn('content', ctx)
        self.assertIsNotNone(ctx['content'])

    # Test: Context processor returns None when no WebsiteContent exists
    def test_returns_none_when_empty(self):
        request = self.factory.get('/')
        ctx = footer_content(request)
        self.assertIn('content', ctx)
        self.assertIsNone(ctx['content'])

    # Test: Footer description is accessible from the returned content
    def test_footer_description_accessible(self):
        WebsiteContent.objects.create(footerDescription="<p>Global footer</p>")
        request = self.factory.get('/')
        ctx = footer_content(request)
        self.assertEqual(ctx['content'].footerDescription, "<p>Global footer</p>")
