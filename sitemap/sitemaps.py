from datetime import date
from django.contrib.sitemaps import Sitemap
from django.urls import reverse

class StaticViewSitemap(Sitemap):
    protocol = "https"
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return [
            "home",
            "practice_areas",
            "about",
            "contact",
            "privacy",
            "payment",
        ]
    
    def location(self, item):
        return reverse(item)
    
    def lastmod(self, item):
        return date.today()