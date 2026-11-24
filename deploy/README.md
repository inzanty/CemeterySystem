# Uruchomienie z trwałym magazynem zdjęć

Z katalogu głównego projektu:

```sh
cp deploy/.env.example deploy/.env
python3 -c 'import secrets; print(secrets.token_urlsafe(64))'
```

Wpisz wygenerowany sekret jako `DJANGO_SECRET_KEY` w `deploy/.env`, a następnie:

```sh
docker compose -f deploy/compose.yaml up --build -d --wait
docker compose -f deploy/compose.yaml exec app python manage.py createsuperuser
```

Aplikacja jest dostępna pod `http://127.0.0.1:8080`. Port można zmienić zmienną
`MEMORIA_PORT`. Konfiguracja uruchamia Gunicorn i Nginx, wyłącza `DEBUG`,
a przy starcie aplikacji wykonuje migracje i `collectstatic`. Obraz używa Python 3.12;
lokalne środowisko Python 3.9 nie wymaga zmiany. Zachowano wersję Django z projektu;
przed publicznym udostępnieniem obowiązuje opisana w głównym README aktualizacja
frameworka do wspieranej wersji.

## Trwałe pliki

Wolumen `data` zawiera SQLite (`/var/lib/memoria/db.sqlite3`) i zdjęcia
(`/var/lib/memoria/media`). Wolumen `static` zawiera wynik `collectstatic`.
Kod aplikacji jest w obrazie, a dane pozostają poza nim. Wymiana obrazu,
restart i `docker compose down` nie usuwają tych wolumenów. Polecenie
`docker compose down -v` usuwa je wraz z danymi — nie używaj go przy aktualizacji.
Używaj tego samego katalogu i nazwy projektu Compose przy kolejnych uruchomieniach.
Stack zaczyna od pustej bazy; lokalne `db.sqlite3` i `media/` nie są kopiowane do obrazu.

Nginx ma dostęp do wolumenów tylko do odczytu i udostępnia wyłącznie `/media/`
i `/static/`. Zdjęcia są publiczne, bez listowania katalogów i wykonywania plików.
Limit żądania Nginx wynosi 6 MiB, aby pomieścić zdjęcie 5 MiB wraz z formularzem;
aplikacja nadal weryfikuje rozmiar, format i liczbę pikseli. Domyślne typy MIME
obrazów oraz `nosniff` ograniczają interpretację plików jako innego typu zawartości.

Aktualizacja i zatrzymanie:

```sh
docker compose -f deploy/compose.yaml up --build -d --wait
docker compose -f deploy/compose.yaml logs --tail=100 app web
docker compose -f deploy/compose.yaml down
```

## Publiczny adres i HTTPS

Port Nginx jest celowo związany z adresem lokalnym. Na docelowym serwerze skieruj
istniejący terminator HTTPS/reverse proxy na `127.0.0.1:8080`, zachowując nagłówek
`Host`. W `deploy/.env` ustaw `DJANGO_ALLOWED_HOSTS` na rzeczywistą domenę
(bez protokołu) i `DJANGO_PUBLIC_SCHEME=https`, po czym odtwórz kontenery.
Ta opcja włącza bezpieczne ciasteczka i rozpoznawanie HTTPS przez Django.
Wewnętrzny Nginx ustawia przekazywany protokół na tę stałą wartość, zamiast ufać
nagłówkowi podanemu przez klienta. Gunicorn nie ma portu publikowanego na hoście.

Bez docelowej domeny i certyfikatu ten zestaw służy do uruchomienia lokalnego
lub jako backend istniejącej infrastruktury HTTPS.

Dokumentacja źródłowa: [wolumeny Docker](https://docs.docker.com/engine/storage/volumes/),
[Gunicorn i Nginx](https://gunicorn.org/deploy/),
[dyrektywa alias Nginx](https://nginx.org/en/docs/http/ngx_http_core_module.html#alias),
[pliki statyczne Django](https://docs.djangoproject.com/en/4.2/howto/static-files/deployment/).
