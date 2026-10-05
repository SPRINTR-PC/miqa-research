from django.utils.translation import gettext_lazy

ETL_SCRIPT_ORIGIN_NATIVE = "native"
ETL_SCRIPT_ORIGIN_CUSTOM = "custom"

ETL_SCRIPT_ORIGIN_CHOICES = [
    (ETL_SCRIPT_ORIGIN_NATIVE, gettext_lazy("Native")),
    (ETL_SCRIPT_ORIGIN_CUSTOM, gettext_lazy("Custom")),
]

ETL_JOB_STATUS_PENDING = "pending"
ETL_JOB_STATUS_RUNNING = "running"
ETL_JOB_STATUS_SUCCEEDED = "succeeded"
ETL_JOB_STATUS_FAILED = "failed"

ETL_JOB_STATUS_CHOICES = [
    (ETL_JOB_STATUS_PENDING, gettext_lazy("Pending")),
    (ETL_JOB_STATUS_RUNNING, gettext_lazy("Running")),
    (ETL_JOB_STATUS_SUCCEEDED, gettext_lazy("Succeeded")),
    (ETL_JOB_STATUS_FAILED, gettext_lazy("Failed")),
]

PIPELINE_BINDING_GROUPING_FILE = "file"
PIPELINE_BINDING_GROUPING_FOLDER = "folder"

PIPELINE_BINDING_GROUPING_CHOICES = [
    (PIPELINE_BINDING_GROUPING_FILE, gettext_lazy("Per file")),
    (PIPELINE_BINDING_GROUPING_FOLDER, gettext_lazy("Folder, with quiescence wait")),
]

PIPELINE_BINDING_RAW_RETENTION_MOVE = "move"
PIPELINE_BINDING_RAW_RETENTION_DELETE = "delete"

PIPELINE_BINDING_RAW_RETENTION_CHOICES = [
    (PIPELINE_BINDING_RAW_RETENTION_MOVE, gettext_lazy("Move to Raw Bucket")),
    (PIPELINE_BINDING_RAW_RETENTION_DELETE, gettext_lazy("Delete after load")),
]

ETL_JOB_INPUT_SOURCE_STATUS_PENDING = "pending"
ETL_JOB_INPUT_SOURCE_STATUS_MOVED = "moved"
ETL_JOB_INPUT_SOURCE_STATUS_DELETED = "deleted"
ETL_JOB_INPUT_SOURCE_STATUS_SOURCE_CLEANUP_PENDING = "source_cleanup_pending"
ETL_JOB_INPUT_SOURCE_STATUS_SOURCE_CLEANUP_STUCK = "source_cleanup_stuck"

ETL_JOB_INPUT_SOURCE_STATUS_CHOICES = [
    (ETL_JOB_INPUT_SOURCE_STATUS_PENDING, gettext_lazy("Not yet moved or deleted")),
    (ETL_JOB_INPUT_SOURCE_STATUS_MOVED, gettext_lazy("Moved")),
    (ETL_JOB_INPUT_SOURCE_STATUS_DELETED, gettext_lazy("Deleted after load")),
    (ETL_JOB_INPUT_SOURCE_STATUS_SOURCE_CLEANUP_PENDING, gettext_lazy("Source cleanup pending (retrying)")),
    (ETL_JOB_INPUT_SOURCE_STATUS_SOURCE_CLEANUP_STUCK, gettext_lazy("Source cleanup stuck (needs manual handling)")),
]
