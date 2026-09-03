from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from MiqaResearch.data.models import ResearchProject


@login_required
async def index(request):
    projects = [
        project
        async for project in ResearchProject.objects.filter(
            researchprojectuserrolemap__user=request.user
        ).distinct()
    ]

    if len(projects) == 1:
        return redirect('dashboard_project', project_id=projects[0].id)

    return render(request, '01_dashboard/index.html', {'projects': projects})
