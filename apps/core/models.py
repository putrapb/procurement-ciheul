from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class DocumentSequence(models.Model):
    """Counter nomor dokumen per prefix dan periode (mis. PR-202610)."""

    key = models.CharField(max_length=30, unique=True)
    last_value = models.PositiveIntegerField(default=0)

    def __str__(self) -> str:
        return f"{self.key}:{self.last_value}"
