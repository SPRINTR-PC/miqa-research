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
