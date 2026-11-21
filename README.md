# Memoria — ewidencja cmentarzy

Aplikacja Django z polskim interfejsem do wyszukiwania osób zmarłych, przeglądania miejsc pochówku i zgłaszania poprawek.

## Uruchomienie

Środowisko projektu: Python 3.9 i Django 4.2. Domyślna baza danych: SQLite.

```sh
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Aplikacja: http://127.0.0.1:8000/ · Panel administratora: `/admin/`.

Opcjonalne dane demonstracyjne: `python manage.py seed_demo`.

## Funkcje i role

- Gość: wyszukiwanie osób, przeglądanie cmentarzy, grobów i pochówków.
- Użytkownik: rejestracja, zgłaszanie poprawek i podgląd własnych zgłoszeń.
- Administrator: zarządzanie ewidencją i rozpatrywanie zgłoszeń. Zaakceptowane poprawki wprowadza ręcznie.

## REST API

Publiczny odczyt list i szczegółów: `/api/cemeteries/`, `/api/graves/`, `/api/deceased/` oraz odpowiadające im adresy `<id>/`.

Wyszukiwanie osób: `q`, `cemetery`, `section`, `death_year_from`, `death_year_to`. Paginacja: `page`, po 20 rekordów na stronę.

## Konfiguracja

Zmienne środowiskowe opisuje `.env.example`; plik `.env` nie jest automatycznie wczytywany. PostgreSQL wymaga instalacji `requirements-postgres.txt` oraz ustawienia `DB_ENGINE=postgresql` i zmiennych `DB_*`.

Konfiguracja domyślna służy do pracy lokalnej. Publiczne wdrożenie wymaga aktualizacji do wspieranych wersji Python/Django i konfiguracji produkcyjnej.
