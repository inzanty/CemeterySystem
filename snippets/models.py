from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
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
    map_x = models.DecimalField("pozycja pozioma (%)", max_digits=5, decimal_places=2,
                               null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(100)])
    map_y = models.DecimalField("pozycja pionowa (%)", max_digits=5, decimal_places=2,
                               null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(100)])

    class Meta:
        verbose_name = "grób"
        verbose_name_plural = "groby"
        ordering = ["section__cemetery__name", "section__name", "row", "number", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["section", "row", "number"], name="unique_grave_location"
            ),
            models.CheckConstraint(
                check=(models.Q(map_x__isnull=True, map_y__isnull=True)
                       | models.Q(map_x__isnull=False, map_y__isnull=False,
                                  map_x__gte=0, map_x__lte=100, map_y__gte=0, map_y__lte=100)),
                name="valid_grave_map_position",
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
    class Type(models.TextChoices):
        CORRECTION = "correction", "Poprawka"
        MISSING_GRAVE = "missing_grave", "Brakujący grób"

    request_type = models.CharField(
        "rodzaj zgłoszenia", max_length=20, choices=Type.choices, default=Type.CORRECTION
    )
    proposed_section = models.ForeignKey(
        Section, verbose_name="proponowany sektor", null=True, blank=True,
        on_delete=models.PROTECT, related_name="missing_grave_requests",
    )
    proposed_row = models.CharField("rząd", max_length=50, blank=True)
    proposed_number = models.CharField("numer grobu", max_length=50, blank=True)
    resulting_grave = models.ForeignKey(
        Grave, verbose_name="utworzony grób", null=True, blank=True,
        on_delete=models.PROTECT, related_name="source_requests",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="rozpatrzył(a)", null=True, blank=True,
        on_delete=models.PROTECT, related_name="reviewed_requests",
    )
    reviewed_at = models.DateTimeField("rozpatrzono", null=True, blank=True)
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
    description = models.TextField("opis zgłoszenia", max_length=4000)
    status = models.CharField(
        "status", max_length=10, choices=Status.choices, default=Status.PENDING
    )
    admin_response = models.TextField(
        "odpowiedź administratora", blank=True, max_length=4000
    )
    created_at = models.DateTimeField("utworzono", auto_now_add=True)
    updated_at = models.DateTimeField("zaktualizowano", auto_now=True)

    class Meta:
        verbose_name = "zgłoszenie"
        verbose_name_plural = "zgłoszenia"
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(request_type="correction", proposed_section__isnull=True,
                             proposed_row="", proposed_number="", resulting_grave__isnull=True)
                    & (models.Q(deceased__isnull=False, grave__isnull=True)
                       | models.Q(deceased__isnull=True, grave__isnull=False))
                ) | (
                    models.Q(request_type="missing_grave", deceased__isnull=True,
                             grave__isnull=True, proposed_section__isnull=False)
                    & ~models.Q(proposed_row="") & ~models.Q(proposed_number="")
                    & (models.Q(status="approved", resulting_grave__isnull=False)
                       | models.Q(status__in=["pending", "rejected"], resulting_grave__isnull=True))
                ),
                name="request_valid_target",
            )
        ]

    def clean(self):
        super().clean()
        if self.request_type == self.Type.CORRECTION:
            if bool(self.deceased_id) == bool(self.grave_id):
                raise ValidationError("Wybierz dokładnie jeden rekord: osobę zmarłą lub grób.")
            if self.proposed_section_id or self.proposed_row or self.proposed_number or self.resulting_grave_id:
                raise ValidationError("Poprawka nie może zawierać proponowanej lokalizacji.")
        elif self.request_type == self.Type.MISSING_GRAVE:
            self.proposed_row = self.proposed_row.strip()
            self.proposed_number = self.proposed_number.strip()
            if self.deceased_id or self.grave_id:
                raise ValidationError("Zgłoszenie brakującego grobu nie może wskazywać rekordu do poprawy.")
            if not (self.proposed_section_id and self.proposed_row and self.proposed_number):
                raise ValidationError("Podaj sektor, rząd i numer grobu.")

    @property
    def is_missing_grave(self):
        return self.request_type == self.Type.MISSING_GRAVE

    @property
    def proposed_location(self):
        return f"{self.proposed_section} — rząd {self.proposed_row}, grób {self.proposed_number}"

    @property
    def subject(self):
        return self.proposed_location if self.is_missing_grave else self.target

    @property
    def target(self):
        return self.deceased if self.deceased_id else self.grave

    def __str__(self):
        return f"Zgłoszenie #{self.pk} — {self.get_status_display()}"

    def get_absolute_url(self):
        return reverse("request-detail", args=[self.pk])


class SavedGrave(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_graves")
    grave = models.ForeignKey(Grave, on_delete=models.CASCADE, related_name="saved_entries")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [models.UniqueConstraint(fields=["user", "grave"], name="unique_saved_grave")]


class GravePhoto(models.Model):
    grave = models.ForeignKey(Grave, on_delete=models.CASCADE, related_name="photos", verbose_name="grób")
    image = models.ImageField("zdjęcie", upload_to="grave_photos/")
    caption = models.CharField("podpis", max_length=300, blank=True)
    uploader = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, verbose_name="dodał(a)")
    uploaded_at = models.DateTimeField("dodano", auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at", "-pk"]
        verbose_name = "zdjęcie grobu"
        verbose_name_plural = "zdjęcia grobów"

    def __str__(self):
        return f"Zdjęcie #{self.pk} — {self.grave}"


class RecordChange(models.Model):
    class Action(models.TextChoices):
        CREATE = "create", "Dodanie"
        UPDATE = "update", "Zmiana"
        DELETE = "delete", "Usunięcie"

    entity_type = models.CharField("rodzaj rekordu", max_length=30)
    entity_id = models.PositiveBigIntegerField("ID rekordu")
    action = models.CharField("czynność", max_length=10, choices=Action.choices)
    editor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, verbose_name="autor")
    timestamp = models.DateTimeField("czas", auto_now_add=True)
    record_label = models.TextField("rekord")
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    before_relations = models.JSONField("nazwy powiązań przed zmianą", default=dict)
    after_relations = models.JSONField("nazwy powiązań po zmianie", default=dict)

    class Meta:
        ordering = ["-timestamp", "-pk"]
        indexes = [models.Index(fields=["entity_type", "entity_id"])]
        verbose_name = "zmiana rekordu"
        verbose_name_plural = "historia rekordów"


class CemeteryPlan(models.Model):
    cemetery = models.OneToOneField(Cemetery, on_delete=models.CASCADE, related_name="plan", verbose_name="cmentarz")
    image = models.ImageField("plan cmentarza", upload_to="cemetery_plans/")
    updated_at = models.DateTimeField("zaktualizowano", auto_now=True)

    class Meta:
        verbose_name = "plan cmentarza"
        verbose_name_plural = "plany cmentarzy"

    def __str__(self):
        return f"Plan — {self.cemetery}"


class GraveFee(models.Model):
    grave = models.OneToOneField(Grave, on_delete=models.CASCADE, related_name="fee", verbose_name="grób")
    valid_until = models.DateField("opłacono do", db_index=True)
    updated_at = models.DateTimeField("zaktualizowano", auto_now=True)

    class Meta:
        ordering = ["valid_until", "pk"]
        verbose_name = "termin opłaty grobu"
        verbose_name_plural = "terminy opłat grobów"

    def __str__(self):
        return f"Opłata — {self.grave}"
