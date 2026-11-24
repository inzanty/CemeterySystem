"""Explicit forms for the moderator's record management screens."""
from django import forms
from django.db import transaction

from .models import Burial, Cemetery, Deceased, Grave, Section


def date_widget():
    return forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})


class PersonChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, person):
        return f"{person} ({person.birth_date:%d.%m.%Y} — {person.death_date:%d.%m.%Y}) · #{person.pk}"


class CemeteryForm(forms.ModelForm):
    class Meta:
        model = Cemetery
        fields = ("name", "address")
        help_texts = {"name": "Np. Cmentarz Centralny", "address": "Np. ul. Lipowa 12, Kraków"}


class SectionForm(forms.ModelForm):
    class Meta:
        model = Section
        fields = ("cemetery", "name")
        help_texts = {"name": "Np. A lub 12"}


class DeceasedForm(forms.ModelForm):
    class Meta:
        model = Deceased
        fields = ("name", "surname", "birth_date", "death_date")
        widgets = {"birth_date": date_widget(), "death_date": date_widget()}
        help_texts = {"name": "Np. Anna", "surname": "Np. Kowalska"}


class BurialForm(forms.ModelForm):
    deceased = PersonChoiceField(label="Osoba zmarła", queryset=Deceased.objects.all())

    class Meta:
        model = Burial
        fields = ("deceased", "grave", "burial_date")
        widgets = {"burial_date": date_widget()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["grave"].queryset = Grave.objects.select_related("section__cemetery")


class GraveForm(forms.ModelForm):
    cemetery = forms.ModelChoiceField(label="Cmentarz", queryset=Cemetery.objects.all())

    class Meta:
        model = Grave
        fields = ("cemetery", "section", "row", "number")
        labels = {"number": "Numer grobu"}
        help_texts = {"row": "Np. 3 lub B", "number": "Np. 24 lub 24A"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial.setdefault("cemetery", self.instance.section.cemetery_id)
        sections = Section.objects.select_related("cemetery")
        cemetery = self.data.get("cemetery") if self.is_bound else self.initial.get("cemetery")
        if cemetery:
            try:
                sections = sections.filter(cemetery_id=int(cemetery))
            except (ValueError, TypeError):
                sections = sections.none()
        self.fields["section"].queryset = sections

    def clean(self):
        data = super().clean()
        cemetery, section = data.get("cemetery"), data.get("section")
        if cemetery and section and section.cemetery_id != cemetery.pk:
            self.add_error("section", "Sektor nie należy do wybranego cmentarza.")
        return data


class GraveCreateForm(GraveForm):
    occupant = forms.ChoiceField(label="Osoba pochowana", initial="none", choices=[
        ("none", "Bez osoby pochowanej"), ("existing", "Wybierz istniejącą osobę"),
        ("new", "Wprowadź nową osobę"),
    ])
    deceased = PersonChoiceField(label="Istniejąca osoba", queryset=Deceased.objects.all(), required=False)
    name = forms.CharField(label="Imię", max_length=100, required=False, help_text="Np. Anna")
    surname = forms.CharField(label="Nazwisko", max_length=100, required=False, help_text="Np. Kowalska")
    birth_date = forms.DateField(label="Data urodzenia", required=False, widget=date_widget())
    death_date = forms.DateField(label="Data śmierci", required=False, widget=date_widget())
    burial_date = forms.DateField(label="Data pochówku", required=False, widget=date_widget())

    def clean(self):
        data = super().clean()
        mode = data.get("occupant")
        required = ["deceased", "burial_date"] if mode == "existing" else (
            ["name", "surname", "birth_date", "death_date", "burial_date"] if mode == "new" else [])
        for field in required:
            if not data.get(field) and field not in self.errors:
                self.add_error(field, "To pole jest wymagane.")
        birth, death = data.get("birth_date"), data.get("death_date")
        if mode == "new" and birth and death and death < birth:
            self.add_error("death_date", "Data śmierci nie może poprzedzać daty urodzenia.")
        if mode == "existing" and data.get("deceased"):
            death = data["deceased"].death_date
        if mode in ("existing", "new") and death and data.get("burial_date") and data["burial_date"] < death:
            self.add_error("burial_date", "Data pochówku nie może poprzedzać daty śmierci.")
        return data

    @transaction.atomic
    def save(self, commit=True):
        if not commit:
            raise ValueError("Guided grave creation must be saved atomically.")
        grave = super().save()
        data = self.cleaned_data
        person = None
        if data["occupant"] == "new":
            person = Deceased(**{key: data[key] for key in ("name", "surname", "birth_date", "death_date")})
            person.full_clean()
            person.save()
        elif data["occupant"] == "existing":
            person = data["deceased"]
        if person:
            burial = Burial(grave=grave, deceased=person, burial_date=data["burial_date"])
            burial.full_clean()
            burial.save()
        return grave


class RecordFilterForm(forms.Form):
    q = forms.CharField(label="Szukaj", required=False, max_length=200,
                        help_text="Nazwa, imię, nazwisko lub lokalizacja grobu.")
    cemetery = forms.ModelChoiceField(label="Cmentarz", queryset=Cemetery.objects.all(),
                                      required=False, empty_label="Wszystkie cmentarze")
