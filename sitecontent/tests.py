from django.test import TestCase
from django.urls import reverse

from sitecontent.models import FAQItem, WebsiteContent


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
