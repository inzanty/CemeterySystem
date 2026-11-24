# Memoria — ewidencja cmentarzy

Aplikacja Django z polskim interfejsem do wyszukiwania osób zmarłych i miejsc pochówku.

## Funkcje

- Wyszukiwanie osób oraz przeglądanie cmentarzy, sektorów, grobów i pochówków.
- Konta użytkowników, prywatna lista zapisanych grobów i zgłaszanie poprawek lub brakujących grobów.
- Panel moderatora do zarządzania ewidencją, zdjęciami i zgłoszeniami oraz przeglądania historii zmian.
- Publiczny REST API oraz jasny, ciemny i systemowy motyw interfejsu.

## Uruchomienie lokalne

Python 3.9 lub 3.12, Django 4.2, domyślnie SQLite. CI i obraz Docker używają Python 3.12.

```sh
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Aplikacja: http://127.0.0.1:8000/ · Administracja: `/admin/` · Moderacja: `/moderator/`.

Opcjonalne dane demonstracyjne: `python manage.py seed_demo`.

## Uprawnienia

Goście mogą przeglądać ewidencję. Zalogowani użytkownicy mogą zapisywać groby,
wysyłać zgłoszenia i śledzić ich status.

Moderator musi mieć aktywne konto w grupie `Moderators`, tworzonej przez migrację.
Grupę przypisuje administrator w `/admin/`. Aktywny superużytkownik również ma
dostęp do moderacji; samo `is_staff` go nie zapewnia.

Akceptacja zgłoszenia brakującego grobu tworzy grób. Zaakceptowane poprawki
moderator wprowadza ręcznie. Decyzje w zgłoszeniach są ostateczne.

## Konfiguracja i wdrożenie

Zmienne środowiskowe opisuje [.env.example](.env.example).
Plik `.env` nie jest automatycznie wczytywany; w PyCharm ustaw zmienne w konfiguracji uruchomienia.

- PostgreSQL: zainstaluj `requirements-postgres.txt` i ustaw `DB_ENGINE=postgresql` oraz zmienne `DB_*`.
- Zdjęcia: katalog `MEDIA_ROOT` (domyślnie `media/`), publiczny adres `/media/`. Obsługiwane JPEG i PNG do 5 MiB i 20 megapikseli.
- Docker, Gunicorn, Nginx i trwałe wolumeny: [instrukcja wdrożenia](deploy/README.md).

Domyślna konfiguracja służy do pracy lokalnej. Przed publicznym wdrożeniem
zaktualizuj Python i Django do wspieranych wersji oraz zapewnij konfigurację
produkcyjną, HTTPS, trwały magazyn zdjęć i kopie zapasowe bazy oraz plików.

## REST API

Publiczny odczyt: `/api/cemeteries/`, `/api/graves/`, `/api/deceased/`.
Szczegóły rekordu: `<endpoint><id>/`.

Filtry osób: `q`, `cemetery`, `section`, `death_year_from`, `death_year_to`.
Paginacja: parametr `page`, po 20 rekordów.

## Testy

W aktywnym środowisku Python; testy JavaScript wymagają Node.js 18+:

```sh
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --noinput
node --test snippets/tests/*.test.cjs
```

[GitHub Actions](.github/workflows/tests.yml) wykonuje te kontrole po każdym pushu
oraz przy otwarciu i aktualizacji pull requestu. Wyniki są dostępne w zakładce Actions.
