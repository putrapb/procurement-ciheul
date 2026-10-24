from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise TypeError("AuditLog bersifat append-only")

    def delete(self):
        raise TypeError("AuditLog bersifat append-only")


class AuditLog(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey("content_type", "object_id")
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="audit_logs"
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self) -> str:
        return f"{self.content_type} #{self.object_id}: {self.from_status} -> {self.to_status}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise TypeError("AuditLog bersifat append-only")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TypeError("AuditLog bersifat append-only")
