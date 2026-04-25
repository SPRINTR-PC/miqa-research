from django.shortcuts import render


def index(request):
    return render(request, '00_landing_page/index.html')
