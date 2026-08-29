from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.views import View
from django.shortcuts import render

class UploadData(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        context = {
            "projects": [
                { "id": "1", "name": "PROTECT-RT"},
                { "id": "2", "name": "ARC-Prostate"},
                { "id": "3", "name": "FLASH-Pediatric"},
            ]
        }
        return render(request, '02_upload_data/index.html', context=context)

    def post(self, request, *args, **kwargs):
        return HttpResponse(status=201)
