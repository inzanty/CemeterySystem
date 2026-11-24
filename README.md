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
- Użytkownik: rejestracja, zgłaszanie poprawek i brakujących grobów oraz podgląd własnych zgłoszeń.
- Moderator: panel `/moderator/` ze statystykami, filtrami, kolejką zgłoszeń i zarządzaniem cmentarzami, sektorami, grobami, osobami zmarłymi oraz pochówkami. Akceptacja brakującego grobu automatycznie tworzy i łączy rekord grobu. Zaakceptowane poprawki wymagają ręcznej aktualizacji ewidencji przez moderatora lub superużytkownika.
- Administrator: zarządzanie ewidencją i przydzielanie moderatorów. Superużytkownik ma również dostęp do panelu moderatora.

Migracja tworzy grupę `Moderators`. W `/admin/` otwórz użytkownika i dodaj go do tej grupy; konto musi być aktywne. Dostęp do moderacji nie wymaga `is_staff`. Samo `is_staff` nie daje prawa do moderacji.

Zgłoszenie brakującego grobu wskazuje istniejący cmentarz i sektor, rząd, numer oraz opis. Nie tworzy osób zmarłych ani pochówków. Istniejąca lokalizacja blokuje wysłanie i akceptację zgłoszenia. Każda decyzja wymaga odpowiedzi, jest ostateczna i zapisuje moderatora oraz czas rozpatrzenia. W Django admin zgłoszenia są dostępne do podglądu z odnośnikiem do panelu moderatora; decyzje zapisuje się wyłącznie w tym panelu.

Moderatorzy i aktywni superużytkownicy mogą również zarządzać cmentarzami,
sektorami, grobami, osobami zmarłymi i pochówkami w `/moderator/`.
Zwykłe konto `is_staff` nie daje dostępu do panelu moderatora.
Formularz nowego grobu pozwala pozostawić grób pusty, wybrać istniejącą osobę
lub utworzyć nową osobę wraz z pochówkiem. Kolejne osoby dodaje się przyciskiem
„Dodaj kolejną osobę” na stronie edycji grobu. Poprawki ze zgłoszeń nadal
wprowadza się ręcznie; rozpatrzone decyzje pozostają ostateczne.
Usunięcie wymaga potwierdzenia i nie usuwa powiązanych rekordów.

## REST API

Publiczny odczyt list i szczegółów: `/api/cemeteries/`, `/api/graves/`, `/api/deceased/` oraz odpowiadające im adresy `<id>/`.

Wyszukiwanie osób: `q`, `cemetery`, `section`, `death_year_from`, `death_year_to`. Paginacja: `page`, po 20 rekordów na stronę.

## Konfiguracja

Zmienne środowiskowe opisuje `.env.example`; plik `.env` nie jest automatycznie wczytywany. PostgreSQL wymaga instalacji `requirements-postgres.txt` oraz ustawienia `DB_ENGINE=postgresql` i zmiennych `DB_*`.

Konfiguracja domyślna służy do pracy lokalnej. Publiczne wdrożenie wymaga aktualizacji do wspieranych wersji Python/Django i konfiguracji produkcyjnej.
