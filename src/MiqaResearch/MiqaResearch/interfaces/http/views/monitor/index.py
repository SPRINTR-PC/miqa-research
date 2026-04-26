from django.shortcuts import render


def index(request):
    return render(request, template_name='04_monitor/index.html')