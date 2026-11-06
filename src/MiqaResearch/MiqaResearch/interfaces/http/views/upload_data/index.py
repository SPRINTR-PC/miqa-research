from django.http import HttpResponse
from django.shortcuts import render
from django.views import View

from helpers.authentication.async_mixins import AsyncLoginRequiredMixin


class UploadData(AsyncLoginRequiredMixin, View):
    async def get(self, request, *args, **kwargs):
        context = {
            "projects": [
                { "id": "1", "name": "PROTECT-RT"},
                { "id": "2", "name": "ARC-Prostate"},
                { "id": "3", "name": "FLASH-Pediatric"},
            ]
        }
        return render(request, '02_upload_data/index.html', context=context)

    async def post(self, request, *args, **kwargs):
        return HttpResponse(status=201)
