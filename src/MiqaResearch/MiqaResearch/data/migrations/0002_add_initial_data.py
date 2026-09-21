import logging
import os

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations
from django.utils.translation import gettext_lazy as _

from contract.constants.research_project_role import (
    PROJECT_ROLE_ADMIN,
    PROJECT_ROLE_ANNOTATOR,
    PROJECT_ROLE_CONTRIBUTOR,
    PROJECT_ROLE_DATA_MANAGER,
    PROJECT_ROLE_INVESTIGATOR,
    PROJECT_ROLE_PI,
)

logger = logging.getLogger(__name__)


def add_default_project_roles(apps, schema_editor):
    # noinspection PyPep8Naming
    ResearchProjectRole = apps.get_model("data", "ResearchProjectRole")

    ResearchProjectRole.objects.bulk_create(
        [
            ResearchProjectRole(
                name=PROJECT_ROLE_ADMIN,
                description=_("Administrator who can manage the research project settings and users connected to the project")),
            ResearchProjectRole(
                name=PROJECT_ROLE_ANNOTATOR,
                description=_("A member of the project who can perform segmentations or in other ways annotate data in the project")),
            ResearchProjectRole(
                name=PROJECT_ROLE_CONTRIBUTOR,
                description=_("A contributor to the study, e.g., research nurses, who are not necessarily directly involved in the analysis of the data")),
            ResearchProjectRole(
                name=PROJECT_ROLE_DATA_MANAGER,
                description=_("Data Manager can manage data and data cleaning for a project")),
            ResearchProjectRole(
                name=PROJECT_ROLE_INVESTIGATOR,
                description=_("A researcher or other investigator connected to the project")),
            ResearchProjectRole(name=PROJECT_ROLE_PI, description=_("Primary Investigator")),
        ]
    )


def add_default_users(apps, schema_editor):
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    # noinspection PyPep8Naming
    User = apps.get_model(app_label, model_name)

    super_user = {
        "email": os.environ.get("MIRES_SU_EMAIL"),
        "password": os.environ.get("MIRES_SU_PASSWORD"),
    }

    user = None
    if not any([val is None for _, val in super_user.items()]):
        user = User(
            username=super_user["email"].split("@")[0],
            email=super_user["email"],
            password=make_password(super_user["password"]),
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )

        user.save()
        user.username = user.id
        user.save()

        logger.info(f"Created superuser {user.username} with email {user.email}")

    if not settings.DEBUG:
        return

    development_users = User.objects.bulk_create([
        User(
            username="staff@example.com",
            email="staff@example.com",
            password=make_password("staff"),
            is_staff=True,
            is_superuser=False,
            is_active=True,
        ),
        User(
            username="projadmin@example.com",
            email="projadmin@example.com",
            password=make_password("projadmin"),
            is_staff=False,
            is_superuser=False,
            is_active=True,
        ),
        User(
            username="annotator@example.com",
            email="annotator@example.com",
            password=make_password("annotator"),
            is_staff=False,
            is_superuser=False,
            is_active=True,
        ),
        User(
            username="contributor@example.com",
            email="contributor@example.com",
            password=make_password("contributor"),
            is_staff=False,
            is_superuser=False,
            is_active=True,
        ),
        User(
            username="datamanager@example.com",
            email="datamanager@example.com",
            password=make_password("datamanager"),
            is_staff=False,
            is_superuser=False,
            is_active=True,
        ),
        User(
            username="investigator@example.com",
            email="investigator@example.com",
            password=make_password("investigator"),
            is_staff=False,
            is_superuser=False,
            is_active=True,
        ),
        User(
            username="pi@example.com",
            email="pi@example.com",
            password=make_password("pi"),
            is_staff=False,
            is_superuser=False,
            is_active=True,
        ),
    ])

    # noinspection PyPep8Naming
    ResearchProject = apps.get_model("data", "ResearchProject")

    project = ResearchProject.objects.create(
        name="SPRINTR PC",
        description="Swedish PRrecision medicine Initiative for Novel Treatment and Research. A national initiative for research and coordination in the development of precision medicine to tailor treatment to the individual's needs.",
    )

    # noinspection PyPep8Naming
    ResearchProjectRole = apps.get_model("data", "ResearchProjectRole")
    # noinspection PyPep8Naming
    ResearchProjectUserRoleMap = apps.get_model("data", "ResearchProjectUserRoleMap")

    if user is not None:
        ResearchProjectUserRoleMap.objects.create(
            user=user,
            project=project,
            role=ResearchProjectRole.objects.get(name=PROJECT_ROLE_ADMIN),
        )
    project_roles = ResearchProjectUserRoleMap.objects.bulk_create([
        ResearchProjectUserRoleMap(
            user=development_users[1],
            project=project,
            role=ResearchProjectRole.objects.get(name=PROJECT_ROLE_ADMIN),
        ),
        ResearchProjectUserRoleMap(
            user=development_users[2],
            project=project,
            role=ResearchProjectRole.objects.get(name=PROJECT_ROLE_ANNOTATOR),
        ),
        ResearchProjectUserRoleMap(
            user=development_users[3],
            project=project,
            role=ResearchProjectRole.objects.get(name=PROJECT_ROLE_CONTRIBUTOR),
        ),
        ResearchProjectUserRoleMap(
            user=development_users[4],
            project=project,
            role=ResearchProjectRole.objects.get(name=PROJECT_ROLE_DATA_MANAGER),
        ),
        ResearchProjectUserRoleMap(
            user=development_users[5],
            project=project,
            role=ResearchProjectRole.objects.get(name=PROJECT_ROLE_INVESTIGATOR),
        ),
        ResearchProjectUserRoleMap(
            user=development_users[6],
            project=project,
            role=ResearchProjectRole.objects.get(name=PROJECT_ROLE_PI),
        ),
    ])


class Migration(migrations.Migration):
    dependencies = [("data", "0001_initial"),]

    operations = [
        migrations.RunPython(add_default_project_roles),
        migrations.RunPython(add_default_users),
    ]
