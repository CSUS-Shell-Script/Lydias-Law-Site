from django.contrib.sitemaps import Sitemap
from django.urls import reverse

class StaticViewSitemap(Sitemap):
    # (url_name, priority, changefreq)
    # Excluded: payment, schedule, services — utility/thin-content pages
    _items = [
        ('home',           1.0, 'weekly'),
        ('about',          0.8, 'monthly'),
        ('practice_areas', 0.9, 'monthly'),
        ('contact',        0.8, 'monthly'),
        ('privacy',        0.3, 'yearly'),
    ]

    def items(self):
        return self._items

    def location(self, item):
        return reverse(item[0])

    def priority(self, item):
        return item[1]

    def changefreq(self, item):
        return item[2]
