"""Conservative duplicate candidates, for human review only."""
from collections import defaultdict
import unicodedata

from django import forms
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .features import page_context
from .models import Burial, Cemetery, Deceased, Grave, Section
from .record_management import moderator_only, record_url


KINDS = {
    "deceased": (Deceased, "Osoby zmarłe", ("name", "surname", "birth_date", "death_date")),
    "grave": (Grave, "Groby", ("section_id", "row", "number")),
    "cemetery": (Cemetery, "Cmentarze", ("name", "address")),
    "section": (Section, "Sektory", ("cemetery_id", "name")),
    "burial": (Burial, "Pochówki", ("deceased_id", "grave_id", "burial_date")),
}


def normalize(value):
    if isinstance(value, str):
        return " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    return value


def duplicate_groups(kind):
    model, _, fields = KINDS[kind]
    groups = defaultdict(list)
    # Select related labels up front instead of issuing queries for every result.
    records = model.objects.order_by("pk")
    related = {"grave": ("section__cemetery",), "section": ("cemetery",),
               "burial": ("deceased", "grave__section__cemetery")}.get(kind, ())
    records = records.select_related(*related) if related else records
    for record in records.iterator(chunk_size=1000):
        key = tuple(normalize(getattr(record, field)) for field in fields)
        groups[key].append(record)
    return [items for items in groups.values() if len(items) > 1]


class DuplicateFilterForm(forms.Form):
    kind = forms.ChoiceField(label="Rodzaj rekordu", choices=[(key, value[1]) for key, value in KINDS.items()])


@moderator_only
@require_http_methods(["GET"])
def duplicate_list(request):
    data = request.GET.copy()
    data.setdefault("kind", "deceased")
    form = DuplicateFilterForm(data)
    groups = duplicate_groups(form.cleaned_data["kind"]) if form.is_valid() else []
    context = page_context(request, groups)
    kind = form.cleaned_data.get("kind", "deceased")
    context["groups"] = [[{"object": obj, "edit_url": record_url(kind, "edit", obj.pk)} for obj in group]
                         for group in context["page_obj"]]
    context.update(form=form, kind=kind)
    return render(request, "snippets/duplicates.html", context)
