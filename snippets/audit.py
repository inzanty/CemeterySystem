"""Request-scoped audit signals. Scripts and seed commands have no actor."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime

from django.db import transaction
from django.db.models.signals import pre_save, post_save, pre_delete, post_delete

from .models import Cemetery, Section, Grave, Deceased, Burial, GravePhoto, RecordChange

_actor = ContextVar("record_editor", default=None)
TRACKED = (Cemetery, Section, Grave, Deceased, Burial, GravePhoto)
TYPE_LABELS = {model._meta.model_name: str(model._meta.verbose_name).capitalize() for model in TRACKED}


@contextmanager
def audit_changes(editor):
    with transaction.atomic():
        token = _actor.set(editor)
        try:
            yield
        finally:
            _actor.reset(token)


def snapshot(instance):
    result = {}
    for field in instance._meta.concrete_fields:
        value = getattr(instance, field.attname)
        if isinstance(value, (date, datetime)):
            value = value.isoformat()
        elif hasattr(value, "name"):
            value = value.name
        result[field.attname] = value
    return result


def remember(sender, instance, **kwargs):
    if _actor.get() is not None:
        previous = sender.objects.filter(pk=instance.pk).first() if instance.pk else None
        instance._audit_before = snapshot(previous) if previous else {}


def write(instance, action, before, after):
    editor = _actor.get()
    if editor is not None and before != after:
        RecordChange.objects.create(entity_type=instance._meta.model_name,
            entity_id=instance.pk, action=action, editor=editor,
            record_label=str(instance), before=before, after=after)


def saved(sender, instance, created, **kwargs):
    if _actor.get() is not None:
        write(instance, "create" if created else "update", getattr(instance, "_audit_before", {}), snapshot(instance))


def deleting(sender, instance, **kwargs):
    write(instance, "delete", snapshot(instance), {})


def remove_file(sender, instance, using, **kwargs):
    if instance.image.name:
        storage, name = instance.image.storage, instance.image.name
        transaction.on_commit(lambda: storage.delete(name), using=using)


def connect():
    for model in TRACKED:
        pre_save.connect(remember, sender=model, dispatch_uid=f"audit_before_{model.__name__}")
        post_save.connect(saved, sender=model, dispatch_uid=f"audit_after_{model.__name__}")
        pre_delete.connect(deleting, sender=model, dispatch_uid=f"audit_delete_{model.__name__}")
    post_delete.connect(remove_file, sender=GravePhoto, dispatch_uid="photo_file_cleanup")
