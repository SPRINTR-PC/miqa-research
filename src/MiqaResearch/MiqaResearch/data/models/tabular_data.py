from uuid import uuid7

from django.db import models


class TabularDataFileSource(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    name = models.CharField(max_length=200, blank=False, null=False, unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = "mires_tabular_data_file_source"
        ordering = ['name']


class RawTabularDataFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    file = models.FileField(upload_to="raw_tabular_data_files/")
    source = models.ForeignKey(TabularDataFileSource, on_delete=models.PROTECT, blank=False, null=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.source

    class Meta:
        db_table = "mires_raw_tabular_data_file"
        ordering = ['-created_at']
