from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import CreateView, DetailView, ListView, TemplateView
from django.views.decorators.http import require_http_methods
from .forms import (CorrectionForm, MissingGraveForm, QueueFilterForm, RegistrationForm,
                    ReviewForm, SearchForm, search_deceased)
from .moderation import is_moderator, review_request
from .models import Cemetery, CorrectionRequest, Deceased, Grave


class HomeView(TemplateView):
    template_name = "snippets/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            cemetery_count=Cemetery.objects.count(),
            deceased_count=Deceased.objects.count(),
            grave_count=Grave.objects.count(),
        )
        return context


class CemeteryListView(ListView):
    model = Cemetery
    paginate_by = 20
    template_name = "snippets/cemetery_list.html"
    queryset = Cemetery.objects.annotate(
        section_count=Count("sections", distinct=True),
        grave_count=Count("sections__graves", distinct=True),
    ).order_by("name", "pk")


class CemeteryDetailView(DetailView):
    model = Cemetery
    template_name = "snippets/cemetery_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sections"] = self.object.sections.annotate(grave_count=Count("graves"))
        return context


class SearchView(ListView):
    template_name = "snippets/search.html"
    paginate_by = 20

    def get_queryset(self):
        self.form = SearchForm(self.request.GET)
        return (
            search_deceased(self.form.cleaned_data)
            if self.form.is_valid()
            else Deceased.objects.none()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.copy()
        query.pop("page", None)
        context.update(form=self.form, filter_query=query.urlencode())
        return context


class DeceasedDetailView(DetailView):
    model = Deceased
    queryset = Deceased.objects.prefetch_related("burials__grave__section__cemetery")
    template_name = "snippets/deceased_detail.html"


class GraveDetailView(DetailView):
    model = Grave
    queryset = Grave.objects.select_related("section__cemetery").prefetch_related(
        "burials__deceased"
    )
    template_name = "snippets/grave_detail.html"


class RegisterView(CreateView):
    form_class = RegistrationForm
    template_name = "registration/register.html"

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        messages.success(self.request, "Konto zostało utworzone.")
        return redirect("request-list")


class RequestListView(LoginRequiredMixin, ListView):
    template_name = "snippets/request_list.html"
    paginate_by = 20

    def get_queryset(self):
        return CorrectionRequest.objects.filter(user=self.request.user).select_related(
            "deceased", "grave__section__cemetery", "proposed_section__cemetery",
            "resulting_grave", "reviewed_by"
        )


class RequestDetailView(LoginRequiredMixin, DetailView):
    template_name = "snippets/request_detail.html"

    def get_queryset(self):
        return CorrectionRequest.objects.filter(user=self.request.user).select_related(
            "deceased", "grave__section__cemetery", "proposed_section__cemetery",
            "resulting_grave", "reviewed_by"
        )


@login_required
@require_http_methods(["GET", "POST"])
def request_create(request, kind, pk):
    model = {"deceased": Deceased, "grave": Grave}.get(kind)
    if model is None:
        from django.http import Http404

        raise Http404
    target = get_object_or_404(model, pk=pk)
    instance = CorrectionRequest(user=request.user, **{kind: target})
    form = CorrectionForm(
        request.POST if request.method == "POST" else None, instance=instance
    )
    if request.method == "POST" and form.is_valid():
        correction = form.save()
        messages.success(request, "Zgłoszenie zostało wysłane do administratora.")
        return redirect(correction)
    return render(
        request, "snippets/request_form.html", {"form": form, "target": target}
    )


@login_required
@require_http_methods(["GET", "POST"])
def missing_grave_create(request):
    instance = CorrectionRequest(user=request.user, request_type=CorrectionRequest.Type.MISSING_GRAVE)
    form = MissingGraveForm(
        request.POST if request.method == "POST" else None,
        instance=instance, initial={"cemetery": request.GET.get("cemetery")},
    )
    if request.method == "POST" and form.is_valid():
        submission = form.save()
        messages.success(request, "Zgłoszenie brakującego grobu zostało wysłane.")
        return redirect(submission)
    return render(request, "snippets/missing_grave_form.html", {"form": form})


@login_required
@require_http_methods(["GET"])
def moderator_dashboard(request):
    if not is_moderator(request.user):
        raise PermissionDenied
    records = CorrectionRequest.objects.all()
    stats = records.aggregate(
        total=Count("pk"),
        pending=Count("pk", filter=Q(status="pending")),
        approved=Count("pk", filter=Q(status="approved")),
        rejected=Count("pk", filter=Q(status="rejected")),
        recent=Count("pk", filter=Q(created_at__gte=timezone.now() - timedelta(days=7))),
    )
    query = request.GET.copy()
    if "status" not in query:
        query["status"] = CorrectionRequest.Status.PENDING
    form = QueueFilterForm(query)
    if form.is_valid():
        for key in ("status", "request_type"):
            if form.cleaned_data[key]:
                records = records.filter(**{key: form.cleaned_data[key]})
    else:
        records = records.none()
    records = records.select_related(
        "user", "deceased", "grave__section__cemetery", "proposed_section__cemetery"
    ).order_by("created_at", "pk")
    page = Paginator(records, 20).get_page(request.GET.get("page"))
    query.pop("page", None)
    return render(request, "snippets/moderator_dashboard.html", {
        "stats": stats, "form": form, "object_list": page.object_list,
        "page_obj": page, "paginator": page.paginator,
        "is_paginated": page.has_other_pages(), "filter_query": query.urlencode(),
    })


@login_required
@require_http_methods(["GET", "POST"])
def moderator_request_detail(request, pk):
    if not is_moderator(request.user):
        raise PermissionDenied
    records = CorrectionRequest.objects.select_related(
        "user", "deceased", "grave__section__cemetery", "proposed_section__cemetery",
        "resulting_grave", "reviewed_by",
    )
    submission = get_object_or_404(records, pk=pk)
    form = ReviewForm(request.POST if request.method == "POST" else None)
    existing = None
    if request.method == "POST" and form.is_valid():
        try:
            review_request(pk, request.user, form.cleaned_data["decision"], form.cleaned_data["admin_response"])
        except ValidationError as error:
            form.add_error(None, error)
            existing = getattr(error, "existing_grave", None)
            submission = records.get(pk=pk)
        else:
            messages.success(request, "Zgłoszenie zostało rozpatrzone.")
            return redirect("moderator-request-detail", pk=pk)
    return render(request, "snippets/moderator_request_detail.html", {
        "object": submission, "form": form, "existing_grave": existing,
    })
