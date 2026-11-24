"""Readable foreign keys without changing the underlying audit snapshots."""
from collections import defaultdict

from .audit import TRACKED

MODELS = {model._meta.model_name: model for model in TRACKED}


def relation_fallbacks(entries):
    wanted = defaultdict(set)
    for entry in entries:
        model = MODELS.get(entry.entity_type)
        if model is None:
            continue
        for field in model._meta.concrete_fields:
            if not field.is_relation:
                continue
            for values, labels in ((entry.before, entry.before_relations), (entry.after, entry.after_relations)):
                value = values.get(field.attname)
                if value is not None and not labels.get(field.attname):
                    wanted[field.related_model].add(value)
    resolved = {}
    for model, ids in wanted.items():
        records = model.objects.filter(pk__in=ids)
        if model._meta.model_name == "grave":
            records = records.select_related("section__cemetery")
        elif model._meta.model_name == "section":
            records = records.select_related("cemetery")
        for record in records:
            resolved[(model, record.pk)] = str(record)
    return resolved


def display_value(field, value, labels, fallbacks):
    if field is None or not field.is_relation or value is None:
        return value
    label = labels.get(field.attname)
    if label:
        return f"{label} (#{value})"
    label = fallbacks.get((field.related_model, value))
    if label:
        return f"{label} (#{value}; nazwa bieżąca)"
    return f"Usunięty rekord (#{value})"
