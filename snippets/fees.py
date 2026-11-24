"""Private in-app fee reminders; no payments or outbound notifications."""
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .audit import audit_changes
from .features import page_context
from .location_forms import FeeFilterForm, GraveFeeForm
from .models import Grave, GraveFee
from .record_management import moderator_only


REMINDER_DAYS = 30


def due_fees(user=None):
    records = GraveFee.objects.select_related("grave__section__cemetery")
    if user is not None:
        records = records.filter(grave__saved_entries__user=user)
    return records


def fee_list(request, moderator=False):
    today = timezone.localdate()
    until = today + timedelta(days=REMINDER_DAYS)
    form = FeeFilterForm(request.GET)
    records = due_fees(None if moderator else request.user)
    if not form.is_valid():
        records = records.none()
    else:
        status = form.cleaned_data["status"]
        if status == "overdue":
            records = records.filter(valid_until__lt=today)
        elif status == "soon":
            records = records.filter(valid_until__range=(today, until))
        elif status != "all":
            records = records.filter(valid_until__lte=until)
    context = page_context(request, records)
    context.update(form=form, today=today, moderator_view=moderator)
    return render(request, "snippets/fee_list.html", context)


@login_required
@require_http_methods(["GET"])
def reminders(request):
    return fee_list(request)


@moderator_only
@require_http_methods(["GET"])
def moderator_fees(request):
    return fee_list(request, moderator=True)


@moderator_only
@require_http_methods(["GET", "POST"])
def fee_edit(request, pk):
    grave = get_object_or_404(Grave.objects.select_related("section__cemetery"), pk=pk)
    fee = GraveFee.objects.filter(grave=grave).first()
    form = GraveFeeForm(request.POST if request.method == "POST" else None, instance=fee)
    if request.method == "POST" and form.is_valid():
        with audit_changes(request.user):
            # Lock the parent even when no fee record exists yet.
            Grave.objects.select_for_update().get(pk=pk)
            current = GraveFee.objects.select_for_update().filter(grave=grave).first()
            if current is None or current.valid_until != form.cleaned_data["valid_until"]:
                current = current or GraveFee(grave=grave)
                current.valid_until = form.cleaned_data["valid_until"]
                current.save()
        messages.success(request, "Zapisano termin opłaty.")
        return redirect("moderator-grave-edit", pk=pk)
    return render(request, "snippets/fee_form.html", {"object": grave, "form": form})
