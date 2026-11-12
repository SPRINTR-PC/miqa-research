"""Real-image DICOM smokes (#423, spec #411): one per sandbox image, on Compose and on Kubernetes.

Each runs a synthetic DICOM file through the real image and loads the rows with the `dicom_instance` loader. The
Python image runs the native `dicom_instance` script (so its imports resolving on the image is also the
conformance check); the R image runs `R_DICOM_SCRIPT`. Opt-in, `long_running`: needs a Docker/Podman daemon
(Compose) or a NetworkPolicy-enforcing cluster with the images loaded (Kubernetes); each skips when absent.
"""
import pytest

from MiqaResearch.data.models import DicomFile, ResearchProject
from tests.dicom_fixtures import build_ct_image, write_dicom
from tests.sandbox_dicom import compose_backend, kubernetes_backend, run_dicom_job

BACKENDS = {"compose": compose_backend, "kubernetes": kubernetes_backend}


@pytest.fixture(autouse=True)
def _keys_and_media(settings, tmp_path):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.mark.long_running
@pytest.mark.django_db
@pytest.mark.parametrize("image_key", ["python-etl-v1", "r-etl-v1"])
@pytest.mark.parametrize("backend_name", list(BACKENDS))
def test_a_dicom_file_runs_through_the_real_image_and_loads(settings, tmp_path, backend_name, image_key):
    backend = BACKENDS[backend_name](settings, image_key)
    project = ResearchProject.objects.create(name=f"Smoke {backend_name} {image_key}", description="")
    folder = tmp_path / "in"
    write_dicom(build_ct_image(patient_id="P-SMOKE-1"), folder / "slice.dcm")

    result, load_result = run_dicom_job(
        backend, project, folder, run_id=f"smoke-{backend_name}-{image_key.split('-')[0]}", image_key=image_key)

    assert load_result.created == 1
    assert DicomFile.objects.filter(research_project=project).count() == 1
