"""Moderator-only HTML record management. Public API remains read-only."""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .management_forms import (BurialForm, CemeteryForm, DeceasedForm, GraveCreateForm,
                               GraveForm, RecordFilterForm, SectionForm)
from .models import Burial, Cemetery, CorrectionRequest, Deceased, Grave, Section
from .moderation import is_moderator
from .audit import audit_changes
from django.db.models import PROTECT


RECORDS = {
    "cemetery": (Cemetery, CemeteryForm, "Cmentarze", "cmentarz", ("name", "address")),
    "section": (Section, SectionForm, "Sektory", "sektor", ("name", "cemetery__name")),
    "grave": (Grave, GraveForm, "Groby", "grób", ("section__cemetery__name", "section__name", "row", "number")),
    "deceased": (Deceased, DeceasedForm, "Osoby zmarłe", "osobę zmarłą", ("name", "surname")),
    "burial": (Burial, BurialForm, "Pochówki", "pochówek", ("deceased__name", "deceased__surname", "grave__section__cemetery__name", "grave__section__name", "grave__row", "grave__number")),
}


def moderator_only(view):
    @login_required
    @wraps(view)
    def checked(request, *args, **kwargs):
        if not is_moderator(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return checked


def record_url(kind, action, pk=None):
    return reverse(f"moderator-{kind}-{action}", args=[pk] if pk is not None else [])


def linked_record(record):
    for kind, (model, *_) in RECORDS.items():
        if isinstance(record, model):
            return {"label": str(record), "url": record_url(kind, "edit", record.pk)}
    if isinstance(record, CorrectionRequest):
        return {"label": str(record), "url": reverse("moderator-request-detail", args=[record.pk])}
    return {"label": str(record), "url": ""}


@moderator_only
@require_http_methods(["GET"])
def record_list(request, kind):
    model, _, title, _, search_fields = RECORDS[kind]
    records = model.objects.all()
    if kind == "section":
        records = records.select_related("cemetery")
    elif kind == "grave":
        records = records.select_related("section__cemetery")
    elif kind == "burial":
        records = records.select_related("deceased", "grave__section__cemetery")
    form = RecordFilterForm(request.GET)
    if kind not in ("section", "grave", "burial"):
        del form.fields["cemetery"]
    if form.is_valid():
        for word in form.cleaned_data.get("q", "").split():
            condition = Q()
            for field in search_fields:
                condition |= Q(**{f"{field}__icontains": word})
            records = records.filter(condition)
        cemetery = form.cleaned_data.get("cemetery")
        if cemetery:
            field = {"section": "cemetery", "grave": "section__cemetery", "burial": "grave__section__cemetery"}[kind]
            records = records.filter(**{field: cemetery})
    else:
        records = records.none()
    page = Paginator(records, 20).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    rows = [{"object": record, "edit_url": record_url(kind, "edit", record.pk),
             "delete_url": record_url(kind, "delete", record.pk)} for record in page]
    return render(request, "snippets/record_list.html", {
        "title": title, "form": form, "rows": rows, "create_url": record_url(kind, "create"),
        "page_obj": page, "paginator": page.paginator, "is_paginated": page.has_other_pages(),
        "filter_query": query.urlencode(),
    })


@moderator_only
@require_http_methods(["GET", "POST"])
def record_form(request, kind, pk=None):
    model, form_class, title, singular, _ = RECORDS[kind]
    record = get_object_or_404(model, pk=pk) if pk is not None else None
    guided = kind == "grave" and record is None
    if guided:
        form_class = GraveCreateForm
    initial = {}
    if kind == "burial" and record is None:
        grave = Grave.objects.filter(pk=request.GET.get("grave")).first() if request.GET.get("grave", "").isdigit() else None
        if grave:
            initial["grave"] = grave.pk
    form = form_class(request.POST if request.method == "POST" else None, instance=record, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            with audit_changes(request.user):
                record = form.save()
        except ValidationError as error:
            form.add_error(None, "; ".join(error.messages))
        except IntegrityError:
            form.add_error(None, "Nie można zapisać rekordu. Sprawdź, czy sektor lub lokalizacja grobu już istnieje.")
        else:
            messages.success(request, "Zapisano rekord.")
            return redirect(record_url(kind, "edit", record.pk))
    for name, field in form.fields.items():
        descriptions = []
        if field.help_text:
            descriptions.append(f"id_{name}_helptext")
        if name in form.errors:
            field.widget.attrs["aria-invalid"] = "true"
            descriptions.append(f"id_{name}_errors")
        if descriptions:
            field.widget.attrs["aria-describedby"] = " ".join(descriptions)
    context = {"form": form, "object": record, "title": f"{'Edytuj' if pk else 'Dodaj'} {singular}",
               "list_url": record_url(kind, "list"), "list_title": title,
               "guided": guided, "is_grave": kind == "grave", "is_cemetery": kind == "cemetery"}
    if pk:
        context["history_kind"] = kind
    if kind == "grave":
        from .photo_forms import GravePhotoForm
        context["photo_form"] = GravePhotoForm()
        context["sections_data"] = list(Section.objects.values("id", "cemetery_id", "name"))
        context["location_fields"] = [form[key] for key in ("cemetery", "section", "row", "number")]
        if guided:
            context["occupant_fields"] = [form[key] for key in ("occupant", "deceased", "name", "surname", "birth_date", "death_date", "burial_date")]
        if pk:
            context["burials"] = record.burials.select_related("deceased")
            context["add_burial_url"] = record_url("burial", "create") + f"?grave={pk}"
    return render(request, "snippets/record_form.html", context)


@moderator_only
@require_http_methods(["GET", "POST"])
def record_delete(request, kind, pk):
    model, _, _, singular, _ = RECORDS[kind]
    record = get_object_or_404(model, pk=pk)
    blocked = []
    if request.method == "POST":
        try:
            with audit_changes(request.user):
                record.delete()
        except ProtectedError as error:
            blocked = sorted((linked_record(item) for item in error.protected_objects), key=lambda item: item["label"])
        else:
            messages.success(request, "Usunięto rekord.")
            return redirect(record_url(kind, "list"))
    else:
        # Only protected relations block deletion; photos and saved entries cascade.
        for relation in model._meta.related_objects:
            if relation.on_delete is not PROTECT:
                continue
            for item in getattr(record, relation.get_accessor_name()).all():
                blocked.append(linked_record(item))
    return render(request, "snippets/record_delete.html", {
        "object": record, "title": f"Usuń {singular}", "blocked": blocked,
        "cancel_url": record_url(kind, "edit", pk),
    })
