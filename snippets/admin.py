from django.contrib import admin
from django.utils.html import format_html
from .models import Burial, Cemetery, CorrectionRequest, Deceased, Grave, Section

admin.site.site_header = "Administracja cmentarzy"
admin.site.site_title = "Cmentarze — administracja"
admin.site.index_title = "Zarządzanie ewidencją"


@admin.register(Cemetery)
class CemeteryAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "public_record")
    search_fields = ("name", "address")

    @admin.display(description="Widok publiczny")
    def public_record(self, obj):
        return format_html('<a href="{}">Zobacz rekord</a>', obj.get_absolute_url())


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("name", "cemetery")
    list_filter = ("cemetery",)
    search_fields = ("name", "cemetery__name")
    autocomplete_fields = ("cemetery",)
    list_select_related = ("cemetery",)


@admin.register(Grave)
class GraveAdmin(admin.ModelAdmin):
    list_display = ("number", "row", "section", "public_record")
    list_filter = ("section__cemetery", "section")
    search_fields = ("number", "row", "section__name", "section__cemetery__name")
    autocomplete_fields = ("section",)
    list_select_related = ("section__cemetery",)
    public_record = CemeteryAdmin.public_record


@admin.register(Deceased)
class DeceasedAdmin(admin.ModelAdmin):
    list_display = ("surname", "name", "birth_date", "death_date", "public_record")
    search_fields = ("name", "surname")
    list_filter = ("death_date",)
    date_hierarchy = "death_date"
    public_record = CemeteryAdmin.public_record


@admin.register(Burial)
class BurialAdmin(admin.ModelAdmin):
    list_display = ("deceased", "grave", "burial_date")
    list_filter = ("grave__section__cemetery", "burial_date")
    search_fields = ("deceased__name", "deceased__surname", "grave__number")
    autocomplete_fields = ("deceased", "grave")
    list_select_related = ("deceased", "grave__section__cemetery")


@admin.register(CorrectionRequest)
class CorrectionRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "request_type", "user", "subject", "status", "created_at", "review_link")
    list_filter = ("status", "request_type", "created_at")
    search_fields = ("description", "user__username", "deceased__surname", "grave__number", "proposed_number")
    readonly_fields = tuple(field.name for field in CorrectionRequest._meta.fields) + ("review_link",)
    fields = readonly_fields
    list_select_related = ("user", "deceased", "grave__section__cemetery", "proposed_section__cemetery")

    @admin.display(description="Rozpatrywanie zgłoszenia")
    def review_link(self, obj):
        from django.urls import reverse
        return format_html('<a href="{}">Otwórz w panelu moderatora</a>',
                           reverse("moderator-request-detail", args=[obj.pk]))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
