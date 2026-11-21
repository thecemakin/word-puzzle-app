# Backend Yol Haritası (`be-roadmap.md`)

Çok oyunculu, sıra tabanlı ve çok dilli kelime oyunu backend geliştirme planı ve takip listesi.

---

## Onaylanan Mimari Kararlar

- **Oyun Temposu:** Sıra tabanlı (asenkron). Oyun oluşturulurken hamle süresi seçilir: `12`, `24`, `48`, `72` saat (oyun boyunca değiştirilemez).
- **Dil Ayrımı:**
  - `User.ui_language`: Kullanıcının ayarlardan seçtiği uygulama/bildirim dili.
  - `Game.language`: Oyun kurulurken seçilen ve oyun boyunca sabit kalan oyun dili (`tr`, `en` başlangıç dilleri; yeni diller oyun motoruna dokunmadan eklenebilir).
- **Altyapı (Geliştirme):** OrbStack üzerinde **PostgreSQL** (`docker-compose.yml`).
- **Redis Stratejisi:** MVP aşamasında zorunlu değil. WebSocket yayın katmanı `EventBroadcaster` arayüzü arkasına soyutlanacak (`InMemoryBroadcaster`), çoklu worker / rate-limit / push kuyruğu aşamasında `RedisBroadcaster` eklenecek.
- **Süre Aşımı (Timeout) Kaynağı:** PostgreSQL'deki `turn_expires_at` (`TIMESTAMPTZ`, UTC) tek gerçek kaynak (source of truth) olacak.
- **Hata Yönetimi:** Tüm API hataları istemcinin `ui_language` ayarına göre çevirebileceği standart `error_code` formatında dönecek.

---

## Hedef Klasör Yapısı

```text
word-puzzle-app/
├── docs/
│   ├── be-roadmap.md
│   └── api/                    # REST, WebSocket ve error_code sözleşme dokümanları
├── alembic/
├── data/
│   └── dictionaries/           # tr.txt, en.txt (genişletilebilir)
├── app/
│   ├── main.py                 # FastAPI giriş noktası & lifespan
│   ├── core/
│   │   ├── config.py           # Ortam değişkenleri (.env / pydantic-settings)
│   │   ├── constants.py        # 15x15 bonus matrisi, izinli süreler, oyun sabitleri
│   │   ├── security.py         # Şifre hashleme ve JWT üretimi/doğrulaması
│   │   └── exceptions.py       # Standart error_code tabanlı uygulama hataları
│   ├── db/
│   │   ├── base.py             # SQLAlchemy DeclarativeBase
│   │   └── session.py          # AsyncEngine & AsyncSession
│   ├── engine/                 # Saf Python (DB & FastAPI bağımsız)
│   │   ├── locales/            # Dil profilleri (tr, en) ve registry
│   │   ├── dictionary.py       # Bellek içi (frozenset) sözlük yükleyici/doğrulayıcı
│   │   ├── bag.py              # Taş torbası (çekme, karıştırma, değiştirme)
│   │   ├── board.py            # 15x15 tahta kuralları ve kelime çıkarma
│   │   ├── scorer.py           # Harf/kelime çarpanları, bingo ve oyun sonu puanlama
│   │   └── rules.py            # Hamle doğrulama, joker, pas ve bitiş kuralları
│   ├── models/                 # SQLAlchemy modelleri (user, game, game_player, move)
│   ├── schemas/                # Pydantic request/response ve WS olay şemaları
│   ├── services/               # İş akışları (auth, user, game, matchmaking, timeout)
│   ├── realtime/               # EventBroadcaster arayüzü (InMemory -> ileride Redis)
│   └── api/
│       ├── deps.py             # get_db, get_current_user
│       ├── routes/             # auth.py, users.py, games.py
│       └── ws.py               # WebSocket bağlantı ve oda yöneticisi
├── tests/
│   ├── engine/                 # Saf oyun motoru birim testleri
│   └── api/                    # REST ve WebSocket entegrasyon testleri
├── docker-compose.yml
├── alembic.ini
├── .env.example
└── requirements.txt
```

---

## Faz 0 — Proje İskeleti ve Geliştirme Ortamı

- [x] Python `.venv` oluşturma ve `fastapi[standard]` kurulumu
- [x] Temel `.gitignore` ve `requirements.txt` dosyalarının oluşturulması
- [x] Gerekli backend bağımlılıklarının eklenmesi (`sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `pyjwt`, `pwdlib`/`argon2-cffi`, `pytest`, `pytest-asyncio`, `ruff`)
- [x] `docker-compose.yml` ile OrbStack uyumlu PostgreSQL kurulumu ve `.env.example` hazırlanması
- [x] Kök dizindeki `main.py` dosyasının `app/` paket yapısına taşınması ve `app/core/config.py` oluşturulması
- [x] `app/db/base.py`, `app/db/session.py` ve `alembic/` async migration kurulumunun tamamlanması
- [x] `/health` endpoint'inin veritabanı bağlantısını kontrol edecek şekilde güncellenmesi

---

## Faz 1 — Saf Oyun Motoru (`app/engine/`) ve Çoklu Dil Altyapısı

- [x] `app/core/constants.py`: 15x15 bonus tahtası (`DL`, `TL`, `DW`, `TW`, merkez `START`), el boyutu (`7`), bingo bonusu (`50`), izinli süre seçenekleri (`12, 24, 48, 72`)
- [x] `app/engine/locales/`: `LanguagePack` veri yapısı ve dil kayıt defteri (`registry`)
  - [x] Türkçe (`tr`) harf havuzu, puanları ve Türkçe-duyarlı normalizasyon (`i -> İ`, `ı -> I`)
  - [x] İngilizce (`en`) harf havuzu, puanları ve normalizasyon
- [x] `app/engine/dictionary.py`: Uygulama açılışında dil bazlı sözlükleri belleğe (`frozenset`) yükleme ve doğrulama
- [x] `data/dictionaries/`: Geliştirme/test için `tr.txt` ve `en.txt` sözlük dosyalarının yerleştirilmesi
- [x] `app/engine/bag.py`: Dil paketine göre taş torbası üretimi, rastgele çekim ve taş değiştirme (`SWAP`)
- [x] `app/engine/board.py`:
  - [x] Tahta sınırları ve dolu kare kontrolü
  - [x] İlk hamlenin merkez kareden `(7, 7)` geçme kuralı
  - [x] Tek satır/sütun hizalama, boşluksuz süreklilik ve mevcut taşlara temas kuralı
  - [x] Ana kelime ve oluşan tüm çapraz kelimelerin koordinatlarıyla çıkarılması
- [x] `app/engine/scorer.py`:
  - [x] Harf (`DL`, `TL`) ve kelime (`DW`, `TW`) çarpanlarının yalnızca yeni yerleştirilen taşlara uygulanması
  - [x] Joker (boş) taşların 0 puan sayılması
  - [x] 7 taşın tamamı oynandığında bingo bonusu eklenmesi
  - [x] Oyun sonu elde kalan taşların puan düşümü / rakibe aktarımı
- [x] `app/engine/rules.py`: Hamle doğrulama orkestrasyonu, joker harf atama kontrolü, ardışık pas ve oyun bitiş koşulları
- [x] `tests/engine/`: Türkçe karakterler, çapraz kelimeler, joker, çift/üçlü çarpanlar, bingo, pas ve oyun sonu senaryoları için kapsamlı unit testler

---

## Faz 2 — Veritabanı Modelleri ve Migration (`app/models/`)

- [x] `User` modeli (`id`, `username`, `email`, `password_hash`, `ui_language`, `is_active`, `created_at`, `updated_at`)
- [x] `Game` modeli (`id`, `language`, `turn_duration_hours`, `status`, `board_state` JSONB, `tile_bag` JSONB, `current_turn_user_id`, `turn_expires_at` UTC, `consecutive_passes`, `move_count`, `version`, `winner_id`, `created_at`, `finished_at`)
  - [x] Aktif oyunlarda süre aşımı sorgusu için `turn_expires_at` üzerinde partial index (`WHERE status = 'active'`)
- [x] `GamePlayer` modeli (`id`, `game_id`, `user_id`, `seat_order`, `rack` JSONB, `score`, `joined_at`)
- [x] `Move` modeli (`id`, `game_id`, `user_id`, `move_number`, `move_type` [`PLAY`, `PASS`, `SWAP`, `RESIGN`, `TIMEOUT`], `placements` JSONB, `words_formed` JSONB, `score_gained`, `created_at`)
- [x] İlk Alembic migration'ın oluşturulması ve OrbStack PostgreSQL üzerinde uygulanıp doğrulanması

---

## Faz 3 — Kimlik Doğrulama, Kullanıcı Ayarları ve Hata Standartları

- [x] `app/core/exceptions.py`: Makine-okunur `error_code` tabanlı global exception handler (`INVALID_WORD`, `NOT_YOUR_TURN`, `INVALID_PLACEMENT`, `GAME_EXPIRED`, `UNSUPPORTED_LANGUAGE`, vb.)
- [x] `app/core/security.py`: Güvenli şifre hashleme ve JWT access/refresh token mekanizması
- [x] `app/api/deps.py`: `get_db` ve `get_current_user` dependency'leri
- [x] `app/api/routes/auth.py`:
  - [x] `POST /api/v1/auth/register`
  - [x] `POST /api/v1/auth/login`
  - [x] `POST /api/v1/auth/refresh`
- [x] `app/api/routes/users.py`:
  - [x] `GET /api/v1/users/me`
  - [x] `PATCH /api/v1/users/me` (`ui_language` ve profil ayarlarını güncelleme)

---

## Faz 4 — Oyun Servisi ve REST API (`app/services/`, `app/api/routes/games.py`)

- [x] `GET /api/v1/games/options`: Desteklenen oyun dillerini (`tr`, `en`...) ve izinli süre seçeneklerini (`12, 24, 48, 72`) dönen metadata endpoint'i
- [x] `POST /api/v1/games`: Yeni oyun oluşturma (`language`, `turn_duration_hours`, opsiyonel `opponent_username` ile davet veya açık oyun)
- [x] `POST /api/v1/games/{game_id}/join`: Bekleyen oyuna katılma, taşların dağıtılması, başlangıç oyuncusunun belirlenmesi ve ilk `turn_expires_at` ayarlanması
- [x] `GET /api/v1/games`: Kullanıcının bekleyen, aktif ve tamamlanmış oyunlarının listelenmesi
- [x] `GET /api/v1/games/{game_id}`: Oyuncuya özel filtrelenmiş oyun durumu (anti-cheat: sadece kendi taşları görünür; rakip taşları ve torba içeriği gizli, sadece adetleri döner)
- [x] `POST /api/v1/games/{game_id}/moves`:
  - [x] `SELECT ... FOR UPDATE` / `version` kontrolü ile eşzamanlı hamle (race condition) koruması
  - [x] `PLAY` (kelime oynama), `PASS` (pas geçme), `SWAP` (taş değiştirme), `RESIGN` (teslim olma) akışları
  - [x] Her hamlede `turn_expires_at` güncellemesi ve oyun bitiş kontrolü
- [x] `GET /api/v1/games/{game_id}/moves`: Hamle geçmişi ve `since_move_number` parametresi ile bağlantı sonrası senkronizasyon

---

## Faz 5 — Gerçek Zamanlı İletişim (WebSocket) ve Süre Aşımı (Timeout)

- [x] `app/realtime/broadcaster.py`: `EventBroadcaster` protokolü ve `InMemoryBroadcaster` implementasyonu
- [x] `app/api/ws.py`:
  - [x] WebSocket bağlantısında JWT doğrulama ve oyun odası yetkilendirmesi
  - [x] Oyun olaylarının yayını (`game_started`, `move_made`, `game_finished`, `turn_expired`)
  - [x] Oyuncuya özel veri sızdırmama (broadcast payload'larında rakip eli yer almaz)
- [x] `app/services/timeout_service.py`: `turn_expires_at <= NOW()` olan aktif oyunları tespit edip hükmen sonuçlandıran periyodik arka plan görevi
- [x] Bildirim kancası (`NotificationHook` arayüzü): Hamle sırası geldiğinde veya süre bitimine yaklaşıldığında `User.ui_language` bilgisiyle ileride FCM/APNs bağlanabilecek soyut katman

---

## Faz 6 — Eşleştirme (Matchmaking), API Dokümantasyonu, Test ve Kod Kalitesi

- [x] `POST /api/v1/games/matchmaking`: Seçilen `language` ve `turn_duration_hours` kriterine göre bekleyen açık oyuna otomatik eşleştirme (yoksa yeni açık oyun oluşturma)
- [x] **API Dokümantasyonu (OpenAPI & Sözleşme):**
  - [x] `app/main.py` ve `app/schemas/`: OpenAPI metadata, `openapi_tags`, JWT `Bearer` şeması, `Field` açıklamaları ve `ErrorResponse` / payload örneklerinin eklenmesi
  - [x] `app/api/routes/`: Tüm REST uçlarında `summary`, `description` ve standart `error_code` hata `responses` tanımları
  - [x] `docs/api/`: Statik sözleşme dokümanlarının yazılması (`overview.md`, `errors.md` hata kodu sözlüğü, `rest-endpoints.md` akış örnekleri, `websocket.md` olay şemaları)
  - [x] `tests/api/`: `/openapi.json` şema doğrulama testi (tüm uçlarda `summary`, `response_model` ve hata şeması kontrolü)
- [x] `tests/api/`: Auth, kullanıcı `ui_language` güncelleme, oyun kurma (`tr`/`en` + süre), hamle yapma, anti-cheat gizlilik, eşzamanlı hamle ve WebSocket entegrasyon testleri
- [x] `ruff` lint/format konfigürasyonu ve yapılandırılmış loglama (structured logging)

---

## Faz 7 — İleri Aşama ve Ölçekleme (İhtiyaç Duyulduğunda)

- [ ] **Redis entegrasyonu:** `RedisBroadcaster` ile çoklu worker WebSocket Pub/Sub, API rate limiting ve çevrimiçi durum (presence)
- [ ] **Push Bildirimleri:** FCM / APNs entegrasyonu (sıra bildirimi ve son saat hatırlatması, kullanıcının `ui_language` tercihine göre)
- [ ] **Yeni Dil Paketleri:** Ek dillerin (`de`, `es`, `fr` vb.) sadece yeni dil profili + sözlük dosyası eklenerek devreye alınması
- [ ] **İleri Oyun Özellikleri:** Bot rakip / kelime ipucu için `Trie`/`DAWG` veri yapısı, istatistikler ve ELO/sıralama sistemi
