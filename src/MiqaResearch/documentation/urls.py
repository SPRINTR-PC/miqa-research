from django.urls import path, register_converter
from django.views.generic import RedirectView

from documentation import views
from documentation.converters import PagePathConverter

register_converter(PagePathConverter, "manualpage")

app_name = "manuals"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="manuals:page"), {"manual": "user"}, name="index"),
    path("<slug:manual>/", views.page, name="page"),
    path("<slug:manual>/<manualpage:page>/", views.page, name="page"),
]
