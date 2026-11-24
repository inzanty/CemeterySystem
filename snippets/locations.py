"""Public cemetery plans and moderator-only plan/marker editing."""
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.http import Http404
from django.views.decorators.http import require_http_methods

from .audit import audit_changes
from .location_forms import CemeteryPlanForm, GravePositionForm
from .models import Cemetery, CemeteryPlan, Grave
from .record_management import moderator_only


def map_context(cemetery, selected=None):
    plan = CemeteryPlan.objects.filter(cemetery=cemetery).first()
    markers = Grave.objects.filter(section__cemetery=cemetery, map_x__isnull=False,
                                   map_y__isnull=False).select_related("section") if plan else []
    return {"cemetery": cemetery, "plan": plan, "markers": markers, "selected_grave": selected}


@require_http_methods(["GET"])
def cemetery_map(request, pk):
    cemetery = get_object_or_404(Cemetery, pk=pk)
    selected = None
    grave_id = request.GET.get("grave", "")
    if grave_id:
        if not grave_id.isdecimal() or len(grave_id) > 19 or int(grave_id) > 9223372036854775807:
            raise Http404
        selected = get_object_or_404(Grave, pk=int(grave_id), section__cemetery=cemetery)
    return render(request, "snippets/cemetery_map.html", map_context(cemetery, selected))


@moderator_only
@require_http_methods(["GET", "POST"])
def plan_edit(request, pk):
    cemetery = get_object_or_404(Cemetery, pk=pk)
    plan = CemeteryPlan.objects.filter(cemetery=cemetery).first()
    old_name = plan.image.name if plan else ""
    form = CemeteryPlanForm(request.POST or None, request.FILES or None, instance=plan)
    if request.method == "POST" and form.is_valid():
        saved_plan = None
        try:
            with audit_changes(request.user):
                # Serialize plan replacement and marker writes for this cemetery.
                Cemetery.objects.select_for_update().get(pk=pk)
                current = CemeteryPlan.objects.select_for_update().filter(cemetery=cemetery).first()
                graves = Grave.objects.select_for_update().filter(section__cemetery=cemetery, map_x__isnull=False)
                if graves.exists() and not form.cleaned_data["reset_positions"]:
                    form.add_error("reset_positions", "Nowy plan zmienia układ mapy. Potwierdź usunięcie znaczników.")
                else:
                    old_name = current.image.name if current else ""
                    saved_plan = current or CemeteryPlan(cemetery=cemetery)
                    saved_plan.image = form.cleaned_data["image"]
                    saved_plan.save()
                    for grave in graves:
                        grave.map_x = grave.map_y = None
                        grave.save(update_fields=["map_x", "map_y"])
                    if old_name and old_name != saved_plan.image.name:
                        storage = saved_plan.image.storage
                        transaction.on_commit(lambda: storage.delete(old_name), robust=True)
        except Exception as error:
            if saved_plan and saved_plan.image._committed and saved_plan.image.name != old_name:
                saved_plan.image.storage.delete(saved_plan.image.name)
            if not isinstance(error, (IntegrityError, OSError)):
                raise
            form.add_error(None, "Nie udało się zapisać planu. Spróbuj ponownie.")
        else:
            if not form.errors:
                messages.success(request, "Zapisano plan cmentarza.")
                return redirect("cemetery-map", pk=pk)
    context = map_context(cemetery)
    context.update(form=form, has_positions=Grave.objects.filter(section__cemetery=cemetery, map_x__isnull=False).exists())
    return render(request, "snippets/plan_form.html", context)


@moderator_only
@require_http_methods(["GET", "POST"])
def position_edit(request, pk):
    grave = get_object_or_404(Grave.objects.select_related("section__cemetery"), pk=pk)
    cemetery = grave.section.cemetery
    plan = CemeteryPlan.objects.filter(cemetery=cemetery).first()
    form = GravePositionForm(request.POST if request.method == "POST" else None, instance=grave,
                             initial={"plan_revision": plan.image.name if plan else ""})
    if request.method == "POST" and form.is_valid():
        with audit_changes(request.user):
            Cemetery.objects.select_for_update().get(pk=cemetery.pk)
            current = Grave.objects.select_for_update().select_related("section").get(pk=pk)
            if current.section.cemetery_id != cemetery.pk:
                form.add_error(None, "Lokalizacja grobu została zmieniona. Odśwież stronę.")
            else:
                current_plan = CemeteryPlan.objects.filter(cemetery=cemetery).first()
                if form.cleaned_data["plan_revision"] != (current_plan.image.name if current_plan else ""):
                    form.add_error(None, "Plan cmentarza został zmieniony. Odśwież stronę i ustaw znacznik ponownie.")
                elif form.cleaned_data["map_x"] is not None and not current_plan:
                    form.add_error(None, "Najpierw dodaj plan tego cmentarza.")
            if not form.errors:
                current.map_x, current.map_y = form.cleaned_data["map_x"], form.cleaned_data["map_y"]
                current.save(update_fields=["map_x", "map_y"])
        if not form.errors:
            messages.success(request, "Zapisano pozycję grobu na planie.")
            return redirect("moderator-grave-edit", pk=pk)
    context = map_context(cemetery, grave)
    context.update(object=grave, form=form)
    return render(request, "snippets/position_form.html", context)
