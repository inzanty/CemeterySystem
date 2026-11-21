from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Cemetery, CorrectionRequest, Deceased, Section


class SearchForm(forms.Form):
    q = forms.CharField(
        label="Imię lub nazwisko",
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={"placeholder": "np. Anna Kowalska"}),
    )
    cemetery = forms.ModelChoiceField(
        label="Cmentarz",
        queryset=Cemetery.objects.all(),
        required=False,
        empty_label="Wszystkie cmentarze",
    )
    section = forms.ModelChoiceField(
        label="Sektor",
        queryset=Section.objects.select_related("cemetery"),
        required=False,
        empty_label="Wszystkie sektory",
    )
    death_year_from = forms.IntegerField(
        label="Rok śmierci od", min_value=1, max_value=9999, required=False
    )
    death_year_to = forms.IntegerField(
        label="Rok śmierci do", min_value=1, max_value=9999, required=False
    )

    def clean(self):
        data = super().clean()
        start, end = data.get("death_year_from"), data.get("death_year_to")
        if start and end and start > end:
            raise forms.ValidationError(
                "Początek zakresu nie może być późniejszy niż jego koniec."
            )
        cemetery, section = data.get("cemetery"), data.get("section")
        if cemetery and section and section.cemetery_id != cemetery.pk:
            self.add_error("section", "Sektor nie należy do wybranego cmentarza.")
        return data


def search_deceased(data):
    records = Deceased.objects.prefetch_related("burials__grave__section__cemetery")
    from django.db.models import Q

    for word in data.get("q", "").split():
        records = records.filter(Q(name__icontains=word) | Q(surname__icontains=word))
    locations = {}
    if data.get("cemetery"):
        locations["burials__grave__section__cemetery"] = data["cemetery"]
    if data.get("section"):
        locations["burials__grave__section"] = data["section"]
    if locations:
        records = records.filter(**locations)
    if data.get("death_year_from"):
        records = records.filter(death_date__year__gte=data["death_year_from"])
    if data.get("death_year_to"):
        records = records.filter(death_date__year__lte=data["death_year_to"])
    return records.distinct()


class RegistrationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username",)


class CorrectionForm(forms.ModelForm):
    class Meta:
        model = CorrectionRequest
        fields = ("description",)
        widgets = {
            "description": forms.Textarea(
                attrs={
                    "rows": 6,
                    "placeholder": "Opisz błąd i podaj prawidłowe informacje oraz źródło, jeśli jest dostępne.",
                }
            )
        }
