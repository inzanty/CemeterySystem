from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from snippets import api, views

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
    path("api/", include(router.urls)),
    path("admin/", admin.site.urls),
]
