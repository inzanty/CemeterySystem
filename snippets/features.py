"""Saved graves, public photos and moderator history HTML endpoints."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .audit import audit_changes, TYPE_LABELS, TRACKED
from .models import Grave, GravePhoto, SavedGrave, RecordChange
from .photo_forms import GravePhotoForm
from .record_management import moderator_only


@login_required
@require_http_methods(["POST"])
def save_grave(request, pk):
    grave = get_object_or_404(Grave, pk=pk)
    SavedGrave.objects.get_or_create(user=request.user, grave=grave)
    return redirect(grave)


@login_required
@require_http_methods(["POST"])
def unsave_grave(request, pk):
    grave = get_object_or_404(Grave, pk=pk)
    SavedGrave.objects.filter(user=request.user, grave=grave).delete()
    return redirect(grave)


def page_context(request, records):
    page = Paginator(records, 20).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    return dict(page_obj=page, paginator=page.paginator, is_paginated=page.has_other_pages(),
                filter_query=query.urlencode())


@login_required
@require_http_methods(["GET"])
def saved_graves(request):
    records = SavedGrave.objects.filter(user=request.user).select_related("grave__section__cemetery")
    return render(request, "snippets/saved_graves.html", page_context(request, records))


@moderator_only
@require_http_methods(["POST"])
def photo_upload(request, pk):
    grave = get_object_or_404(Grave, pk=pk)
    form = GravePhotoForm(request.POST, request.FILES)
    if form.is_valid():
        photo = form.save(commit=False)
        photo.grave, photo.uploader = grave, request.user
        try:
            with audit_changes(request.user):
                photo.save()
        except Exception as error:
            # File storage is not transactional. Compensate even if audit insertion fails.
            if photo.image.name and photo.image._committed:
                photo.image.storage.delete(photo.image.name)
            if not isinstance(error, (IntegrityError, OSError)):
                raise
            form.add_error(None, "Nie udało się zapisać zdjęcia. Spróbuj ponownie.")
        else:
            messages.success(request, "Dodano zdjęcie.")
            return redirect("moderator-grave-edit", pk=pk)
    return render(request, "snippets/photo_upload.html", {"object": grave, "form": form}, status=400)


@moderator_only
@require_http_methods(["GET", "POST"])
def photo_delete(request, pk):
    photo = get_object_or_404(GravePhoto.objects.select_related("grave__section__cemetery"), pk=pk)
    grave_id = photo.grave_id
    if request.method == "POST":
        with audit_changes(request.user):
            photo.delete()
        messages.success(request, "Usunięto zdjęcie.")
        return redirect("moderator-grave-edit", pk=grave_id)
    return render(request, "snippets/photo_delete.html", {"object": photo})


@moderator_only
@require_http_methods(["GET"])
def history(request):
    records = RecordChange.objects.select_related("editor")
    kind, action = request.GET.get("type", ""), request.GET.get("action", "")
    entity_id = request.GET.get("record", "")
    if kind:
        records = records.filter(entity_type=kind)
    if action:
        records = records.filter(action=action)
    if entity_id:
        records = records.filter(entity_id=int(entity_id)) if entity_id.isdecimal() and len(entity_id) < 19 else records.none()
    context = page_context(request, records)
    rows = []
    for entry in context["page_obj"]:
        model = next((m for m in TRACKED if m._meta.model_name == entry.entity_type), None)
        labels = {f.attname: str(f.verbose_name) for f in model._meta.fields} if model else {}
        changes = []
        for key in sorted(entry.before.keys() | entry.after.keys()):
            before, after = entry.before.get(key), entry.after.get(key)
            if before != after:
                changes.append({"label": labels.get(key, key), "before": before, "after": after})
        rows.append({"entry": entry, "changes": changes, "type_label": TYPE_LABELS.get(entry.entity_type, entry.entity_type)})
    context.update(rows=rows, types=TYPE_LABELS.items(), actions=RecordChange.Action.choices,
                   selected_type=kind, selected_action=action, record_id=entity_id)
    return render(request, "snippets/history.html", context)
