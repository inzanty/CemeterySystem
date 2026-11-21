from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse


class Cemetery(models.Model):
    name = models.CharField("nazwa", max_length=200)
    address = models.CharField("adres", max_length=255, blank=True)

    class Meta:
        verbose_name = "cmentarz"
        verbose_name_plural = "cmentarze"
        ordering = ["name", "pk"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("cemetery-detail", args=[self.pk])


class Section(models.Model):
    cemetery = models.ForeignKey(
        Cemetery,
        verbose_name="cmentarz",
        on_delete=models.PROTECT,
        related_name="sections",
    )
    name = models.CharField("nazwa", max_length=100)

    class Meta:
        verbose_name = "sektor"
        verbose_name_plural = "sektory"
        ordering = ["cemetery__name", "name", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["cemetery", "name"], name="unique_section_per_cemetery"
            )
        ]

    def __str__(self):
        return f"{self.cemetery} — sektor {self.name}"


class Grave(models.Model):
    section = models.ForeignKey(
        Section, verbose_name="sektor", on_delete=models.PROTECT, related_name="graves"
    )
    row = models.CharField("rząd", max_length=50)
    number = models.CharField("numer", max_length=50)

    class Meta:
        verbose_name = "grób"
        verbose_name_plural = "groby"
        ordering = ["section__cemetery__name", "section__name", "row", "number", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["section", "row", "number"], name="unique_grave_location"
            )
        ]

    def __str__(self):
        return f"{self.section} — rząd {self.row}, grób {self.number}"

    def get_absolute_url(self):
        return reverse("grave-detail", args=[self.pk])


class Deceased(models.Model):
    name = models.CharField("imię", max_length=100)
    surname = models.CharField("nazwisko", max_length=100)
    birth_date = models.DateField("data urodzenia")
    death_date = models.DateField("data śmierci")

    class Meta:
        verbose_name = "osoba zmarła"
        verbose_name_plural = "osoby zmarłe"
        ordering = ["surname", "name", "pk"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(death_date__gte=models.F("birth_date")),
                name="valid_life_dates",
            )
        ]

    def clean(self):
        super().clean()
        if self.birth_date and self.death_date and self.death_date < self.birth_date:
            raise ValidationError(
                {"death_date": "Data śmierci nie może poprzedzać daty urodzenia."}
            )
        if (
            self.pk
            and self.death_date
            and self.burials.filter(burial_date__lt=self.death_date).exists()
        ):
            raise ValidationError(
                {
                    "death_date": "Data śmierci nie może być późniejsza niż istniejący pochówek."
                }
            )

    def __str__(self):
        return f"{self.name} {self.surname}"

    def get_absolute_url(self):
        return reverse("deceased-detail", args=[self.pk])


class Burial(models.Model):
    deceased = models.ForeignKey(
        Deceased,
        verbose_name="osoba zmarła",
        on_delete=models.PROTECT,
        related_name="burials",
    )
    grave = models.ForeignKey(
        Grave, verbose_name="grób", on_delete=models.PROTECT, related_name="burials"
    )
    burial_date = models.DateField("data pochówku")

    class Meta:
        verbose_name = "pochówek"
        verbose_name_plural = "pochówki"
        ordering = ["-burial_date", "pk"]

    def clean(self):
        super().clean()
        if self.deceased_id and self.burial_date:
            deceased = Deceased.objects.filter(pk=self.deceased_id).first()
            if deceased and self.burial_date < deceased.death_date:
                raise ValidationError(
                    {"burial_date": "Data pochówku nie może poprzedzać daty śmierci."}
                )

    def __str__(self):
        return f"{self.deceased} — {self.grave}"


class CorrectionRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Oczekujące"
        APPROVED = "approved", "Zaakceptowane"
        REJECTED = "rejected", "Odrzucone"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="użytkownik",
        on_delete=models.PROTECT,
        related_name="correction_requests",
    )
    deceased = models.ForeignKey(
        Deceased,
        verbose_name="osoba zmarła",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
    grave = models.ForeignKey(
        Grave, verbose_name="grób", null=True, blank=True, on_delete=models.PROTECT
    )
    description = models.TextField("opis proponowanej poprawki", max_length=4000)
    status = models.CharField(
        "status", max_length=10, choices=Status.choices, default=Status.PENDING
    )
    admin_response = models.TextField(
        "odpowiedź administratora", blank=True, max_length=4000
    )
    created_at = models.DateTimeField("utworzono", auto_now_add=True)
    updated_at = models.DateTimeField("zaktualizowano", auto_now=True)

    class Meta:
        verbose_name = "zgłoszenie poprawki"
        verbose_name_plural = "zgłoszenia poprawek"
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(deceased__isnull=False, grave__isnull=True)
                    | models.Q(deceased__isnull=True, grave__isnull=False)
                ),
                name="correction_exactly_one_target",
            )
        ]

    def clean(self):
        super().clean()
        if bool(self.deceased_id) == bool(self.grave_id):
            raise ValidationError(
                "Wybierz dokładnie jeden rekord: osobę zmarłą lub grób."
            )

    @property
    def target(self):
        return self.deceased if self.deceased_id else self.grave

    def __str__(self):
        return f"Zgłoszenie #{self.pk} — {self.get_status_display()}"

    def get_absolute_url(self):
        return reverse("request-detail", args=[self.pk])
