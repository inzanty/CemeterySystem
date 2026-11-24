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
Usunięcie wymaga potwierdzenia; chronione rekordy blokują operację. Zdjęcia i zapisane wpisy grobu są usuwane kaskadowo.

## REST API

Publiczny odczyt list i szczegółów: `/api/cemeteries/`, `/api/graves/`, `/api/deceased/` oraz odpowiadające im adresy `<id>/`.

Wyszukiwanie osób: `q`, `cemetery`, `section`, `death_year_from`, `death_year_to`. Paginacja: `page`, po 20 rekordów na stronę.

## Konfiguracja

Zmienne środowiskowe opisuje `.env.example`; plik `.env` nie jest automatycznie wczytywany. PostgreSQL wymaga instalacji `requirements-postgres.txt` oraz ustawienia `DB_ENGINE=postgresql` i zmiennych `DB_*`.

Konfiguracja domyślna służy do pracy lokalnej. Publiczne wdrożenie wymaga aktualizacji do wspieranych wersji Python/Django i konfiguracji produkcyjnej.

## Zapisane groby, zdjęcia i historia

Zalogowany użytkownik może zapisywać groby na stronie szczegółów i przeglądać
„Moje zapisane groby” (`/saved-graves/`, 20 wpisów na stronę). Zapisanie i usunięcie
wpisu wymaga POST z CSRF; wielokrotne wykonanie jest bezpieczne. Wpisy są prywatne
i znikają po usunięciu użytkownika lub grobu.

Zdjęcia są publiczne na stronie grobu. Dodawać i usuwać je mogą wyłącznie aktywni
moderatorzy i superużytkownicy, na stronie edycji grobu. Usunięcie wymaga
potwierdzenia. Obsługiwane są nieruchome JPEG i PNG do 5 MiB (5 × 1024² bajtów)
i 20 000 000 pikseli. Pillow sprawdza zawartość i ponownie koduje obraz, usuwając
metadane. Nazwy plików są generowane przez aplikację. Usunięcie zdjęcia lub grobu
usuwa plik dopiero po zatwierdzeniu transakcji; nieudany zapis rekordu zdjęcia
usuwa nowy plik. Zdjęcia i zapisane wpisy są usuwane kaskadowo; istniejące relacje
chronione (np. pochówki i zgłoszenia) nadal blokują usunięcie grobu.

`MEDIA_ROOT` wskazuje katalog zdjęć (domyślnie `media/`, pomijany w Git);
`MEDIA_URL` ma wartość `/media/`. Serwer Django udostępnia pliki lokalnie tylko
przy `DEBUG=True`. W produkcji skonfiguruj serwer WWW lub magazyn obiektowy do
publicznego odczytu `/media/`, bez wykonywania przesłanych plików. Zapewnij trwały
wolumen, prawa zapisu dla aplikacji i kopie zapasowe plików wraz z bazą danych.
`collectstatic` nie kopiuje zdjęć. Nowa instalacja wymaga `pip install -r requirements.txt`
i `python manage.py migrate`.

Historia (`/moderator/history/`, 20 wpisów na stronę) jest dostępna wyłącznie dla
aktywnych moderatorów i superużytkowników, również przy podglądzie w Django admin.
Zapisuje utworzenie, rzeczywistą zmianę i usunięcie cmentarza, sektora, grobu,
osoby zmarłej i pochówku oraz dodanie/usunięcie zdjęcia. Obejmuje panel moderatora,
Django admin (także usuwanie zbiorcze), tworzenie grobu z osobą i pochówkiem oraz
akceptację zgłoszenia brakującego grobu. Wpis zawiera autora, czas, nazwę rekordu,
identyfikator i wartości pól przed/po zmianie. Daty mają format ISO 8601,
a klucze obce są liczbami ID. Brak zmian nie tworzy wpisu; wycofanie transakcji
wycofuje również historię. Historia pozostaje po usunięciu rekordu i nie ma akcji
edycji ani usuwania w aplikacji lub adminie. Po usunięciu konta autora pozostaje
historia z pustym autorem.

Historia zaczyna się po instalacji migracji; nie odtwarza dawnych zdarzeń.
Zapisy prywatnych grobów, komendy seed i bezpośrednie operacje ORM/skryptów nie
są objęte historią przypisywaną użytkownikowi. Publiczny REST API pozostaje bez zmian.

Weryfikacja: `python manage.py test` oraz `python manage.py check`.
