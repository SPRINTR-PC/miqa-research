"""Orphan DICOM blob sweep (#420, design on #407): a blob under DICOM/ with no DicomFile row is
reported after the detect age and deleted after the grace age, only if it was already reportable at
the previous run. Tests run against both DicomStorage backends (local disk, moto S3)."""
import datetime
import os
from uuid import uuid4

import boto3
import pytest
from django.core import mail
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.utils import timezone
from moto import mock_aws

from contract.constants.audit_log import EVENT_TYPE_DICOM_ORPHAN_SWEEP
from MiqaResearch.actions.dicom_ingest.orphan_sweep import sweep_orphans
from MiqaResearch.data.models import (
    AuditLog,
    DicomFile,
    DicomSeries,
    DicomStudy,
    ParticipantKey,
    ResearchProject,
    StudyParticipant,
)
from MiqaResearch.data.models.dicom_storage import DicomStorage

H = datetime.timedelta(hours=1)
NOW = timezone.now()


class Blobs:
    """Writes blobs whose last-modified is `age` before NOW, on whichever backend is active."""

    def __init__(self, kind, monkeypatch):
        self.kind, self.ages = kind, {}
        if kind == "s3":
            # moto stamps LastModified at put time; substitute the intended age in the listing
            real = DicomStorage.iter_blobs
            ages = self.ages

            def iter_blobs(storage, prefix=""):
                for name, size, _ in real(storage, prefix):
                    yield name, size, NOW - ages[name]
            monkeypatch.setattr(DicomStorage, "iter_blobs", iter_blobs)

    def put(self, age, name=None, size=10):
        name = name or f"DICOM/2026/11/{uuid4()}/{uuid4()}.dcm"
        DicomStorage().save(name, ContentFile(b"x" * size))
        self.ages[name] = age
        if self.kind == "local":
            t = (NOW - age).timestamp()
            os.utime(DicomStorage().path(name), (t, t))
        return name

    def names(self):
        return {n for n, _, _ in DicomStorage().iter_blobs("DICOM/")}


@pytest.fixture(params=["local", "s3"])
def blobs(request, settings, tmp_path, monkeypatch):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.DICOM_ORPHAN_DETECT_HOURS = 2
    settings.DICOM_ORPHAN_GRACE_HOURS = 24
    settings.DICOM_ORPHAN_MAX_DELETE_COUNT = 100
    settings.DICOM_ORPHAN_MAX_DELETE_FRACTION = 1.0
    settings.NO_REPLY_EMAIL_ADDRESS = "noreply@example.test"
    if request.param == "s3":
        settings.DICOM_STORAGE_BACKEND = "s3"
        settings.DICOM_S3_BUCKET = "dicom-storage"
        settings.DICOM_S3_ENDPOINT_URL = None
        settings.DICOM_S3_REGION_NAME = "us-east-1"
        with mock_aws():
            boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="dicom-storage")
            yield Blobs("s3", monkeypatch)
    else:
        yield Blobs("local", monkeypatch)


@pytest.fixture(autouse=True)
def encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(
        username="staffer", password="x", email="staff@example.test", is_staff=True)


def _row_for(name):
    project = ResearchProject.objects.create(name=f"p-{uuid4().hex[:6]}", description="-")
    participant = StudyParticipant.objects.create(alias1=f"a-{uuid4().hex[:8]}", research_project=project)
    key = ParticipantKey.objects.create(
        project=project, key_type="dicom:PatientID", value=f"p-{uuid4().hex[:8]}", study_participant=participant)
    study = DicomStudy.objects.create(
        participant_key=key, study_datetime=NOW, study_instance_uid=f"1.2.{uuid4().int % 10**10}")
    series = DicomSeries.objects.create(study=study, series_instance_uid=f"1.3.{uuid4().int % 10**10}")
    row = DicomFile.objects.create(
        series=series, sop_instance_uid=f"1.4.{uuid4().int % 10**10}", file_size_in_mb=1.0, file="placeholder")
    DicomFile.objects.filter(pk=row.pk).update(file=name)
    return row


def _run(**kwargs):
    kwargs.setdefault("delete", True)
    return sweep_orphans(**kwargs)


def test_iter_blobs_yields_name_size_and_aware_last_modified_under_the_prefix(blobs):
    kept = blobs.put(3 * H)
    blobs.put(H, name="other/x.bin")

    listed = list(DicomStorage().iter_blobs("DICOM/"))

    assert [(n, s) for n, s, _ in listed] == [(kept, 10)]
    assert listed[0][2].tzinfo is not None


def test_first_run_reports_old_orphans_but_deletes_nothing(blobs, db):
    young = blobs.put(H)
    old = blobs.put(30 * H)

    result = _run(now=NOW)

    assert result.reportable == 1  # only `old`; `young` is under the detect age
    assert result.deleted == 0
    assert blobs.names() == {young, old}


def test_blob_with_a_row_is_not_an_orphan(blobs, db):
    name = blobs.put(30 * H)
    _row_for(name)

    assert _run(now=NOW).reportable == 0


def test_second_run_deletes_only_blobs_past_grace_that_were_reportable_at_the_previous_run(blobs, db):
    ripe = blobs.put(30 * H)               # past grace, and was reportable (28h) at the previous run
    pending = blobs.put(10 * H)            # reportable but under grace
    fresh = blobs.put(3 * H)               # became reportable only since the previous run
    young = blobs.put(H)
    _run(now=NOW - 2 * H)                  # previous run: first ever, deletes nothing
    assert blobs.names() == {ripe, pending, fresh, young}

    result = _run(now=NOW)

    # fresh is 3h old: not older than previous_run(2h ago) - detect(2h) = 4h. ripe: 30h > 24h and > 4h.
    assert blobs.names() == {pending, fresh, young}
    assert result.deleted == 1


def test_blob_past_grace_but_not_yet_reportable_at_the_previous_run_survives(blobs, db):
    never_notified = blobs.put(25 * H)  # 1h old at the run 24h ago: not reportable then
    notified = blobs.put(30 * H)        # 6h old at the run 24h ago: reportable then
    _run(now=NOW - 24 * H)

    result = _run(now=NOW)

    assert blobs.names() == {never_notified}
    assert result.deleted == 1 and notified not in blobs.names()


def test_dry_run_never_deletes_emails_or_audits(blobs, staff):
    blobs.put(30 * H)
    _run(now=NOW - 2 * H)
    mail.outbox.clear()
    audits_before = AuditLog.objects.filter(event_type=EVENT_TYPE_DICOM_ORPHAN_SWEEP).count()

    result = _run(now=NOW, delete=False, notify=False, record=False)

    assert result.deleted == 0 and result.deletable == 1
    assert len(blobs.names()) == 1
    assert mail.outbox == []
    assert AuditLog.objects.filter(event_type=EVENT_TYPE_DICOM_ORPHAN_SWEEP).count() == audits_before


def test_breaker_trips_on_count_and_force_overrides(blobs, settings, db):
    settings.DICOM_ORPHAN_MAX_DELETE_COUNT = 2
    names = {blobs.put(30 * H) for _ in range(3)}
    _run(now=NOW - 2 * H)

    tripped = _run(now=NOW)
    assert tripped.breaker_tripped and tripped.deleted == 0
    assert blobs.names() == names

    forced = _run(now=NOW, force=True)
    assert not forced.breaker_tripped and forced.deleted == 3
    assert blobs.names() == set()


def test_breaker_trips_on_fraction_of_listed_blobs(blobs, settings, db):
    settings.DICOM_ORPHAN_MAX_DELETE_FRACTION = 0.05
    for _ in range(3):
        _row_for(blobs.put(30 * H))
    orphan = blobs.put(30 * H)  # 1 of 4 listed = 25% > 5%
    _run(now=NOW - 2 * H)

    result = _run(now=NOW)

    assert result.breaker_tripped and result.deleted == 0
    assert orphan in blobs.names()


def test_row_that_appears_just_before_a_delete_saves_the_blob(blobs, db, monkeypatch):
    first, second = blobs.put(30 * H), blobs.put(30 * H)
    _run(now=NOW - 2 * H)
    real_delete, seen = DicomStorage.delete, []

    def delete(storage, name):
        seen.append(name)
        if len(seen) == 1:  # a row for the other blob is committed while we are deleting this one
            _row_for(({first, second} - {name}).pop())
        return real_delete(storage, name)
    monkeypatch.setattr(DicomStorage, "delete", delete)

    result = _run(now=NOW)

    assert result.deleted == 1
    assert len(blobs.names()) == 1


def test_failed_delete_is_counted_and_does_not_stop_the_run(blobs, db, monkeypatch):
    a = blobs.put(30 * H)
    blobs.put(30 * H)
    _run(now=NOW - 2 * H)
    real_delete = DicomStorage.delete

    def delete(storage, name):
        if name == a:
            raise OSError("boom")
        return real_delete(storage, name)
    monkeypatch.setattr(DicomStorage, "delete", delete)

    result = _run(now=NOW)

    assert result.failed == 1 and result.deleted == 1
    assert blobs.names() == {a}


def test_run_emails_staff_with_counts_bytes_and_samples_and_records_one_audit_event(blobs, staff):
    old = [blobs.put(30 * H, size=100) for _ in range(25)]
    _run(now=NOW - 2 * H)
    mail.outbox.clear()

    _run(now=NOW)

    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.to == ["staff@example.test"]
    body = msg.body
    assert "25" in body and "2500" in body
    assert sum(1 for n in old if n in body) == 20  # at most 20 sample keys
    events = AuditLog.objects.filter(event_type=EVENT_TYPE_DICOM_ORPHAN_SWEEP)
    assert events.count() == 2
    meta = events.first().metadata
    assert meta["deleted"] == 25 and meta["bytes"] == 2500 and len(meta["sample_keys"]) == 20
    assert events.first().project is None


def test_email_mentions_breaker_and_pending_deletion_time(blobs, staff, settings):
    settings.DICOM_ORPHAN_MAX_DELETE_COUNT = 0
    blobs.put(30 * H)
    pending = blobs.put(10 * H)
    _run(now=NOW - 2 * H)
    mail.outbox.clear()

    _run(now=NOW)

    body = mail.outbox[0].body.lower()
    assert "circuit breaker" in body
    assert "earliest deletion" in body
    assert pending  # pending blob listed as sample


def test_no_email_when_there_are_no_orphans(blobs, staff):
    _row_for(blobs.put(30 * H))

    _run(now=NOW)

    assert mail.outbox == []


def test_report_action_never_deletes(blobs, staff, settings):
    from MiqaResearch.tasks.dicom_handling.orphan_sweep import sweep_dicom_orphans
    settings.DICOM_ORPHAN_SWEEP_ACTION = "report"
    blobs.put(30 * H)
    sweep_dicom_orphans.func()
    result = sweep_dicom_orphans.func()

    assert result["deleted"] == 0
    assert len(blobs.names()) == 1


def test_beat_task_deletes_when_action_is_delete(blobs, staff, settings):
    from MiqaResearch.tasks.dicom_handling.orphan_sweep import sweep_dicom_orphans
    settings.DICOM_ORPHAN_SWEEP_ACTION = "delete"
    blobs.put(30 * H)
    _run(now=timezone.now() - 2 * H)

    result = sweep_dicom_orphans.func()

    assert result["deleted"] == 1


def test_command_defaults_to_dry_run_without_email_or_audit(blobs, staff, capsys):
    blobs.put(30 * H)
    _run(now=timezone.now() - 2 * H)
    mail.outbox.clear()
    audits = AuditLog.objects.filter(event_type=EVENT_TYPE_DICOM_ORPHAN_SWEEP).count()

    call_command("sweep_dicom_orphans")

    assert len(blobs.names()) == 1
    assert mail.outbox == []
    assert AuditLog.objects.filter(event_type=EVENT_TYPE_DICOM_ORPHAN_SWEEP).count() == audits
    assert "would delete 1" in capsys.readouterr().out.lower()


def test_command_delete_flag_deletes_and_force_overrides_breaker(blobs, staff, settings):
    settings.DICOM_ORPHAN_MAX_DELETE_COUNT = 0
    blobs.put(30 * H)
    _run(now=timezone.now() - 2 * H)

    call_command("sweep_dicom_orphans", "--delete")
    assert len(blobs.names()) == 1
    call_command("sweep_dicom_orphans", "--delete", "--force")
    assert blobs.names() == set()
