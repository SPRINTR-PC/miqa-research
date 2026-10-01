from django.urls import path, register_converter
from django.views.generic import RedirectView

from documentation import views
from documentation.converters import AssetFileConverter, DownloadHashConverter, PagePathConverter

register_converter(PagePathConverter, "manualpage")
register_converter(AssetFileConverter, "manualfile")
register_converter(DownloadHashConverter, "downloadhash")

app_name = "manuals"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="manuals:page"), {"manual": "user"}, name="index"),
    # Assets sit exactly where Sphinx's relative links point; registered before the page route.
    path("<slug:manual>/_images/<manualfile:filename>", views.image, name="image"),
    path("<slug:manual>/_downloads/<downloadhash:digest>/<manualfile:filename>", views.download, name="download"),
    # Registered before the page route, which denies "search" anyway.
    path("<slug:manual>/search/", views.search, name="search"),
    path("<slug:manual>/search/live/", views.search_live, name="search-live"),
    path("<slug:manual>/", views.page, name="page"),
    path("<slug:manual>/<manualpage:page>/", views.page, name="page"),
]
