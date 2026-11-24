"""Forms for cemetery plans, marker positions and fee dates."""
from django import forms

from .management_forms import date_widget
from .models import CemeteryPlan, Grave, GraveFee
from .photo_forms import GravePhotoForm


class CemeteryPlanForm(forms.ModelForm):
    image = forms.FileField(label="Plan cmentarza", help_text="JPEG lub PNG, do 5 MiB i 20 megapikseli.",
                            widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png"}))
    reset_positions = forms.BooleanField(label="Potwierdzam usunięcie dotychczasowych znaczników po zmianie planu",
                                         required=False)

    class Meta:
        model = CemeteryPlan
        fields = ("image",)

    clean_image = GravePhotoForm.clean_image


class GravePositionForm(forms.ModelForm):
    plan_revision = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Grave
        fields = ("map_x", "map_y")
        widgets = {name: forms.NumberInput(attrs={"min": 0, "max": 100, "step": "0.01"})
                   for name in fields}
        help_texts = {"map_x": "0 = lewa krawędź, 100 = prawa krawędź.",
                      "map_y": "0 = górna krawędź, 100 = dolna krawędź. Wyczyść oba pola, aby usunąć znacznik."}

    def clean(self):
        data = super().clean()
        if (data.get("map_x") is None) != (data.get("map_y") is None):
            raise forms.ValidationError("Podaj obie współrzędne albo pozostaw oba pola puste.")
        return data


class GraveFeeForm(forms.ModelForm):
    class Meta:
        model = GraveFee
        fields = ("valid_until",)
        widgets = {"valid_until": date_widget()}


class FeeFilterForm(forms.Form):
    status = forms.ChoiceField(label="Termin", required=False, choices=[
        ("", "Po terminie i w ciągu 30 dni"), ("overdue", "Po terminie"),
        ("soon", "W ciągu 30 dni"), ("all", "Wszystkie terminy"),
    ])
