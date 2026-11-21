from datetime import date
from django.core.management.base import BaseCommand
from django.db import transaction
from snippets.models import Burial, Cemetery, Deceased, Grave, Section


class Command(BaseCommand):
    help = "Dodaje fikcyjne dane demonstracyjne, bez kont i haseł. Można uruchamiać wielokrotnie."

    @transaction.atomic
    def handle(self, *args, **options):
        locations = [
            ("Cmentarz Parkowy — dane demo", "ul. Pamięci 12, Fikcyjne Miasto"),
            ("Cmentarz Leśny — dane demo", "ul. Cisowa 8, Fikcyjne Miasto"),
        ]
        names = [
            ("Anna", "Kowalska"),
            ("Jan", "Nowak"),
            ("Maria", "Zielińska"),
            ("Piotr", "Wiśniewski"),
            ("Helena", "Wójcik"),
            ("Adam", "Kamiński"),
        ]
        for index, (name, surname) in enumerate(names):
            cemetery_name, address = locations[index % 2]
            cemetery, _ = Cemetery.objects.get_or_create(
                name=cemetery_name, defaults={"address": address}
            )
            section, _ = Section.objects.get_or_create(
                cemetery=cemetery, name="A" if index < 3 else "B"
            )
            grave, _ = Grave.objects.get_or_create(
                section=section, row="1", number=str(index + 1)
            )
            person, _ = Deceased.objects.get_or_create(
                name=name,
                surname=surname,
                birth_date=date(1930 + index * 3, 4, 12),
                death_date=date(2000 + index * 3, 8, 20),
            )
            Burial.objects.get_or_create(
                deceased=person, grave=grave, burial_date=date(2000 + index * 3, 8, 24)
            )
        self.stdout.write(
            self.style.SUCCESS(
                "Dodano fikcyjne rekordy demonstracyjne. Nie utworzono kont użytkowników."
            )
        )
