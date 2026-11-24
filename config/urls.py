from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from snippets import api, views, record_management

router = DefaultRouter()
router.register("cemeteries", api.CemeteryViewSet, basename="cemetery-api")
router.register("graves", api.GraveViewSet, basename="grave-api")
router.register("deceased", api.DeceasedViewSet, basename="deceased-api")
urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("cemeteries/", views.CemeteryListView.as_view(), name="cemetery-list"),
    path(
        "cemeteries/<int:pk>/",
        views.CemeteryDetailView.as_view(),
        name="cemetery-detail",
    ),
    path("search/", views.SearchView.as_view(), name="search"),
    path(
        "deceased/<int:pk>/", views.DeceasedDetailView.as_view(), name="deceased-detail"
    ),
    path("graves/<int:pk>/", views.GraveDetailView.as_view(), name="grave-detail"),
    path("accounts/register/", views.RegisterView.as_view(), name="register"),
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path(
        "accounts/logout/",
        auth_views.LogoutView.as_view(http_method_names=["post", "options"]),
        name="logout",
    ),
    path("requests/", views.RequestListView.as_view(), name="request-list"),
    path(
        "requests/<int:pk>/", views.RequestDetailView.as_view(), name="request-detail"
    ),
    path(
        "requests/new/<str:kind>/<int:pk>/", views.request_create, name="request-create"
    ),
    path("requests/missing-grave/", views.missing_grave_create, name="missing-grave-create"),
    path("moderator/", views.moderator_dashboard, name="moderator-dashboard"),
    path("moderator/requests/<int:pk>/", views.moderator_request_detail, name="moderator-request-detail"),
    path("api/", include(router.urls)),
    path("admin/", admin.site.urls),
]

# Explicit named HTML routes share the same moderator authorization on every action.
for kind, slug in (("cemetery", "cemeteries"), ("section", "sections"),
                   ("grave", "graves"), ("deceased", "deceased"), ("burial", "burials")):
    urlpatterns += [
        path(f"moderator/{slug}/", record_management.record_list, {"kind": kind}, name=f"moderator-{kind}-list"),
        path(f"moderator/{slug}/new/", record_management.record_form, {"kind": kind}, name=f"moderator-{kind}-create"),
        path(f"moderator/{slug}/<int:pk>/edit/", record_management.record_form, {"kind": kind}, name=f"moderator-{kind}-edit"),
        path(f"moderator/{slug}/<int:pk>/delete/", record_management.record_delete, {"kind": kind}, name=f"moderator-{kind}-delete"),
    ]
