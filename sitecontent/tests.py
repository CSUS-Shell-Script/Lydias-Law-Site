from django.test import TestCase, RequestFactory, override_settings
from django.urls import reverse
from sitecontent.models import FAQItem, WebsiteContent, PracticeAreaItem
from sitecontent.context_processors import footer_content
from sitecontent.views import _annotate_pa_images


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

# works with either HTTP standard we're bouncing between during development
@override_settings(SECURE_SSL_REDIRECT=False)
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


############################### Practice Area Item Model ###############################

class PracticeAreaTestCase(TestCase):
    """
    sitecontent.0007_seed_practice_areas seeds initial rows. Tests that assume an
    empty table or only their own rows must clear PracticeAreaItem before running.
    """

    def setUp(self):
        super().setUp()
        PracticeAreaItem.objects.all().delete()


class PracticeAreaItemModelTests(PracticeAreaTestCase):

    def test_ordering_uses_display_order_then_id(self):
        second = PracticeAreaItem.objects.create(title="PA2", display_order=2, is_active=True)
        first = PracticeAreaItem.objects.create(title="PA1", display_order=1, is_active=True)
        also_first = PracticeAreaItem.objects.create(title="PA1b", display_order=1, is_active=True)

        ordered_ids = list(PracticeAreaItem.objects.values_list("id", flat=True))
        self.assertEqual(ordered_ids, [first.id, also_first.id, second.id])

    def test_str_with_title(self):
        pa = PracticeAreaItem.objects.create(title="Adoption", display_order=1)
        self.assertEqual(str(pa), "Adoption")

    def test_str_without_title(self):
        pa = PracticeAreaItem.objects.create(title="", display_order=1)
        self.assertEqual(str(pa), f"Practice Area #{pa.pk}")


############################### Practice Area Image Annotation ###############################

class AnnotatePAImagesTests(TestCase):

    def test_image_paths_assigned_sequentially(self):
        items = [PracticeAreaItem(title=f"PA{i}") for i in range(3)]
        annotated = _annotate_pa_images(items)
        self.assertEqual(annotated[0].image_static_path, "images/practice_area_1.png")
        self.assertEqual(annotated[1].image_static_path, "images/practice_area_2.png")
        self.assertEqual(annotated[2].image_static_path, "images/practice_area_3.png")

    def test_image_path_clamped_at_max(self):
        # assume MAX_PA_IMAGES is 9 — items beyond index 8 should reuse practice_area_9.png
        items = [PracticeAreaItem(title=f"PA{i}") for i in range(11)]
        annotated = _annotate_pa_images(items)
        self.assertEqual(annotated[8].image_static_path, "images/practice_area_9.png")
        self.assertEqual(annotated[9].image_static_path, "images/practice_area_9.png")
        self.assertEqual(annotated[10].image_static_path, "images/practice_area_9.png")


############################### Home View Context ###############################

# works with either HTTP standard we're bouncing between during development
@override_settings(SECURE_SSL_REDIRECT=False)
class HomeViewContextTests(PracticeAreaTestCase):

    def setUp(self):
        super().setUp()
        FAQItem.objects.all().delete()
        WebsiteContent.objects.create(
            frontPageHeader="Header",
            frontPageDescription="<p>Description</p>",
        )

    def test_practice_areas_in_context(self):
        PracticeAreaItem.objects.create(title="Adoption", display_order=1, is_active=True)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("practice_areas", response.context)

    def test_only_active_practice_areas_in_context(self):
        PracticeAreaItem.objects.create(title="Active", display_order=1, is_active=True)
        PracticeAreaItem.objects.create(title="Hidden", display_order=2, is_active=False)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        titles = [pa.title for pa in response.context["practice_areas"]]
        self.assertIn("Active", titles)
        self.assertNotIn("Hidden", titles)

    def test_pa_buttons_capped_at_five(self):
        for i in range(6):
            PracticeAreaItem.objects.create(title=f"PA{i + 1}", display_order=i + 1, is_active=True)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["pa_buttons"]), 5)

    def test_pa_buttons_fallback_when_no_active_practice_areas(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        pa_buttons = response.context["pa_buttons"]
        self.assertEqual(len(pa_buttons), 1)
        self.assertEqual(pa_buttons[0].image_static_path, "images/practice_area_1.png")
        self.assertEqual(pa_buttons[0].title, "Practice Areas")
