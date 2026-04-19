from django.test import TestCase, RequestFactory
from django.urls import reverse
from sitecontent.models import FAQItem, WebsiteContent, PracticeAreaItem
from sitecontent.context_processors import footer_content


############################### Website Content Model (LLW-288) ###############################

class WebsiteContentModelTests(TestCase):

    # Test: WebsiteContent can be created with all fields populated
    def test_create_with_all_fields(self):
        content = WebsiteContent.objects.create(
            frontPageHeader="Welcome Header",
            frontPageDescription="<p>Front page description</p>",
            nameTitle="Lydia A. Suprun",
            aboutMeDescription="<p>About me</p>",
            officeLocation="123 Main St",
            phoneNumber="555-123-4567",
            emailAddress="welcome@example.com",
            footerDescription="<p>Footer text</p>",
        )
        PracticeAreaItem.objects.all().delete()
        practice_areas = [
            ("Step-Parent Adoption", "<p>Step-parent</p>"),
            ("Adult Adoption", "<p>Adult</p>"),
            ("Guardianship", "<p>Guardianship</p>"),
            ("Guardianship to Adoption", "<p>G to A</p>"),
            ("Independent Adoption", "<p>Independent</p>"),
        ]
        for order, (title, description) in enumerate(practice_areas, start=1):
            PracticeAreaItem.objects.create(
                title=title,
                description=description,
                display_order=order,
                is_active=True,
            )
        content.refresh_from_db()
        self.assertEqual(content.frontPageHeader, "Welcome Header")
        self.assertEqual(content.frontPageDescription, "<p>Front page description</p>")
        self.assertEqual(content.nameTitle, "Lydia A. Suprun")
        self.assertEqual(content.aboutMeDescription, "<p>About me</p>")
        self.assertEqual(content.officeLocation, "123 Main St")
        self.assertEqual(content.phoneNumber, "555-123-4567")
        self.assertEqual(content.emailAddress, "welcome@example.com")
        self.assertEqual(content.footerDescription, "<p>Footer text</p>")
        self.assertEqual(PracticeAreaItem.objects.count(), 5)
        for title, description in practice_areas:
            self.assertTrue(
                PracticeAreaItem.objects.filter(title=title, description=description, is_active=True).exists()
            )

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



class FAQTestCase(TestCase):
    """
    sitecontent.0005_faqitem seeds initial FAQ rows. Tests that assume an empty
    table or only their own rows must clear FAQItem before running.
    """

    def setUp(self):
        super().setUp()
        FAQItem.objects.all().delete()


class FAQItemModelTests(FAQTestCase):
    def test_ordering_uses_display_order_then_id(self):
        second = FAQItem.objects.create(question="Q2", answer="<p>A2</p>", display_order=2, is_active=True)
        first = FAQItem.objects.create(question="Q1", answer="<p>A1</p>", display_order=1, is_active=True)
        also_first = FAQItem.objects.create(question="Q1b", answer="<p>A1b</p>", display_order=1, is_active=True)

        ordered_ids = list(FAQItem.objects.values_list("id", flat=True))
        self.assertEqual(ordered_ids, [first.id, also_first.id, second.id])


class HomeFAQRenderingTests(FAQTestCase):
    def setUp(self):
        super().setUp()
        WebsiteContent.objects.create(
            frontPageHeader="Header",
            frontPageDescription="<p>Description</p>",
        )

    def test_home_renders_only_active_faqs_in_order(self):
        FAQItem.objects.create(question="Later", answer="<p>later</p>", display_order=2, is_active=True)
        FAQItem.objects.create(question="Hidden", answer="<p>hidden</p>", display_order=1, is_active=False)
        FAQItem.objects.create(question="First", answer="<p>first</p>", display_order=1, is_active=True)

        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "First")
        self.assertContains(response, "Later")
        self.assertNotContains(response, "Hidden")

        faqs = list(response.context["faqs"])
        self.assertEqual([faq.question for faq in faqs], ["First", "Later"])

    def test_home_handles_empty_faq_collection(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "No frequently asked questions are available right now.")
