"""Validation-only forms for the API clients tab (#277). A view calls `is_valid()` and hands
`cleaned_data` to an Action in `MiqaResearch.actions.client_bindings`. The project's Sites are passed
in pre-fetched (a form can't query inside an async view); there is no project field, since a
client's project is the tab's project and never changes.
"""
from django import forms
from django.utils.translation import gettext_lazy as _


class _SiteAndRawMixin(forms.Form):
    clinic = forms.ChoiceField(
        label=_("Site"), required=False,
        help_text=_("Narrows the client to participants with a consent at this Site. Empty: all Sites."))
    dicom_raw = forms.BooleanField(
        label=_("Raw DICOM access (dicom:raw)"), required=False,
        help_text=_("Original files with full PHI from the raw WADO endpoints. Without it the client "
                    "only gets de-identified metadata and frames."))

    def __init__(self, *args, sites, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["clinic"].choices = [("", _("All sites"))] + [
            (str(site["clinic_id"]), site["clinic_name"]) for site in sites]


class ApiClientIssueForm(_SiteAndRawMixin):
    name = forms.CharField(label=_("Name"), max_length=255)

    field_order = ["name", "clinic", "dicom_raw"]


class ApiClientUpdateForm(_SiteAndRawMixin):
    pass
