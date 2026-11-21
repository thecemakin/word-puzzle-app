# 🔠 Word Puzzle App Backend

[![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-red.svg)](https://www.sqlalchemy.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Languages / Diller:**  
> [🇬🇧 English](#-english) | [🇹🇷 Türkçe](#-türkçe)

---

## 🇬🇧 English

### 📖 Overview
**Word Puzzle App** is a high-performance, asynchronous, turn-based multiplayer word game backend built with **FastAPI**, **PostgreSQL**, and **WebSockets**.

Designed for mobile and web cross-platform play, it supports asynchronous turns (12 to 72 hours per turn), real-time game updates, cheat-proof server-side rule verification, and localized word validation for multiple languages (Turkish and English).

---

### ✨ Key Features

- **🎮 Pure Python Rules & Game Engine (`app/engine`)**:
  - Authoritative 15x15 standard grid with bonus cell multipliers (DL, TL, DW, TW).
  - Validates tile placement connectivity, first-move center coverage, contiguous words, and cross-words.
  - High-performance `frozenset` in-memory dictionary lookup.
  - Language-aware letter distributions and points (Turkish special characters: `İ, I, Ş, Ğ, Ü, Ö, Ç` and English standard set).
  - 50-point "Bingo" bonus for placing all 7 rack tiles in a single turn.
- **🛡️ Anti-Cheat & Fair Play**:
  - Opponents' rack tiles and the remaining tile bag sequence are **never** leaked via REST or WebSocket payloads (only tile counts are exposed).
  - All moves, passes, and swaps are verified server-side.
- **⏱️ Asynchronous Turn-Based Architecture**:
  - Flexible per-game turn timers: `12`, `24`, `48`, or `72` hours.
  - Automated background timeout worker processes expired turns and awards forfeits without blocking the API.
- **⚡ Real-Time WebSocket Communication**:
  - Instant notifications for moves, passes, swaps, turn changes, and game completions.
  - Connection lifecycle management releases database connections upon handshake to prevent pool exhaustion.
- **🤝 Quick Matchmaking**:
  - One-click matchmaking endpoint pairs players looking for the same language and turn duration.
- **🔐 Robust Authentication & Security**:
  - Argon2id password hashing.
  - Short-lived JWT Access Tokens + Rotating Refresh Tokens with database revocation.
  - Sliding-window in-memory rate limiting for sensitive endpoints (login, register, moves).
  - Correlation tracking via `X-Request-ID` middleware and structured JSON logging.

---

### 🛠️ Tech Stack

- **Backend Framework:** [FastAPI](https://fastapi.tiangolo.com/) (Python 3.9+)
- **Database:** PostgreSQL 16 (via [asyncpg](https://github.com/MagicStack/asyncpg) & [SQLAlchemy 2.0](https://www.sqlalchemy.org/))
- **Migrations:** [Alembic](https://alembic.sqlalchemy.org/)
- **Security:** Argon2id (`pwdlib`), JWT (`pyjwt`)
- **Testing & Quality:** Pytest, pytest-asyncio, Ruff

---

### 📁 Project Structure

```text
word-puzzle-app/
├── alembic/              # Database migration scripts (Async Alembic)
├── app/
│   ├── api/              # REST routes (auth, users, games) & WebSockets
│   ├── core/             # Configuration, security, logging, rate limiting
│   ├── db/               # SQLAlchemy async engine, base model, sessionmaker
│   ├── engine/           # Pure Python game logic (board, bag, scorer, rules)
│   │   └── locales/      # Language packs (tr, en tile distributions & points)
│   ├── models/           # SQLAlchemy ORM models (User, Game, GamePlayer, Move, etc.)
│   ├── realtime/         # WebSocket connection manager & event broadcaster
│   ├── schemas/          # Pydantic v2 schemas (requests, responses, errors)
│   └── services/         # Business logic (AuthService, GameService, TimeoutService)
├── data/
│   └── dictionaries/     # In-memory dictionary wordlists (tr.txt, en.txt)
├── docs/                 # API specifications, roadmaps, and architecture guides
├── tests/                # Unit and integration test suite
├── docker-compose.yml    # PostgreSQL container definition
└── pyproject.toml        # Ruff, pytest, and project configurations
```

---

### 🚀 Getting Started

#### Prerequisites
- **Python 3.9+**
- **Docker & Docker Compose** (or OrbStack)

#### 1. Clone & Set Up Virtual Environment
```bash
# Clone the repository
git clone https://github.com/your-username/word-puzzle-app.git
cd word-puzzle-app

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

#### 2. Configure Environment Variables
Copy the example environment file and adjust if necessary:
```bash
cp .env.example .env
```

#### 3. Start PostgreSQL Database
```bash
docker compose up -d
```

#### 4. Run Database Migrations
```bash
alembic upgrade head
```

#### 5. Start the Development Server
```bash
fastapi dev app/main.py --port 8000
```
The server will start at `http://127.0.0.1:8000`.

---

### 📚 API Documentation

Once the server is running, you can explore the interactive API documentation:
- **Swagger UI:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc:** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- **OpenAPI Schema:** [http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json)

For detailed documentation, see the [`docs/api/`](docs/api/) directory:
- [API Overview](docs/api/overview.md)
- [REST Endpoints](docs/api/rest-endpoints.md)
- [WebSocket Guide](docs/api/websocket.md)
- [Error Codes](docs/api/errors.md)

---

### 🧪 Running Tests & Linter

```bash
# Run unit and integration tests
pytest -v

# Run code formatting and lint checks
ruff check .
```

---

## 🇹🇷 Türkçe

### 📖 Proje Hakkında
**Word Puzzle App**, **FastAPI**, **PostgreSQL** ve **WebSocket** altyapısıyla geliştirilmiş, yüksek performanslı, asenkron ve sıra tabanlı çok oyunculu kelime oyunu arka uç (backend) servisidir.

Mobil ve web istemcileri için optimize edilmiş olup, oyuncuların gerçek zamanlı bağlanma zorunluluğu olmadan (tur başına 12-72 saat) hamle yapabilmesini sağlar. Sunucu taraflı anti-cheat (hile önleme) mimarisi ve çok dilli (Türkçe ve İngilizce) sözlük doğrulama motoruna sahiptir.

---

### ✨ Temel Özellikler

- **🎮 Saf Python Oyun ve Kural Motoru (`app/engine`)**:
  - Standart 15x15 oyun tahtası ve harf/kelime çarpanları (H2, H3, K2, K3).
  - İlk hamlede merkez kare zorunluluğu, harflerin bitişikliği ve çapraz kelimelerin tam doğrulanması.
  - `frozenset` tabanlı, bellek içi ultra hızlı sözlük kontrolü.
  - Dile duyarlı harf puanları ve torba dağılımları (Türkçe `İ, I, Ş, Ğ, Ü, Ö, Ç` özel karakter uyumluluğu ve İngilizce harf seti).
  - Istakadaki 7 harfin tek hamlede kullanılması durumunda 50 puanlık "Bingo" bonusu.
- **🛡️ Anti-Cheat (Hile Koruması)**:
  - Rakibin elindeki harfler (ıstaka) ve torbada kalan harflerin sırası/içeriği istemcilere **kesinlikle sızdırılmaz** (yalnızca harf adetleri iletilir).
  - Tüm hamle, pas ve harf değiştirme işlemleri sunucu tarafında doğrulanır.
- **⏱️ Asenkron Sıra Tabanlı Yapı**:
  - Oyun bazında seçilebilir hamle süreleri: `12`, `24`, `48` veya `72` saat.
  - Arka planda çalışan otomatik zaman aşımı servisi (`TimeoutService`), süresi dolan hamleleri tespit ederek hükmen mağlubiyet kurallarını uygular.
- **⚡ Gerçek Zamanlı WebSocket Bildirimleri**:
  - Hamleler, pas geçmeler, harf değişimleri ve oyun sonu durumları anlık olarak oyunculara iletilir.
  - El sıkışma (handshake) sonrasında veritabanı bağlantısı havuza geri iade edilerek kaynak tüketimi önlenir.
- **🤝 Hızlı Eşleştirme (Matchmaking)**:
  - Aynı dil ve süre tercihindeki oyuncuları tek tıkla eşleştiren akıllı eşleştirme havuzu.
- **🔐 Kapsamlı Güvenlik & Yetkilendirme**:
  - Argon2id algoritmasıyla güvenli parola özetleme.
  - Kısa ömürlü JWT Access Token + Yenilenen ve veritabanında takip/iptal edilebilen Refresh Token sistemi.
  - Hassas uç noktalar için kayan pencereli (sliding-window) hız sınırlama (rate limiting).
  - `X-Request-ID` takip başlığı ve yapılandırılmış JSON loglama.

---

### 🛠️ Kullanılan Teknolojiler

- **Web Framework:** [FastAPI](https://fastapi.tiangolo.com/) (Python 3.9+)
- **Veritabanı:** PostgreSQL 16 ([asyncpg](https://github.com/MagicStack/asyncpg) ve [SQLAlchemy 2.0 Async](https://www.sqlalchemy.org/))
- **Veritabanı Göçleri (Migrations):** [Alembic](https://alembic.sqlalchemy.org/)
- **Kimlik Doğrulama:** Argon2id (`pwdlib`), JWT (`pyjwt`)
- **Test & Kod Standartları:** Pytest, pytest-asyncio, Ruff

---

### 📁 Proje Dizin Yapısı

```text
word-puzzle-app/
├── alembic/              # Asenkron veritabanı migrasyon dosyaları
├── app/
│   ├── api/              # REST API rotaları (auth, users, games) ve WebSocket
│   ├── core/             # Konfigürasyon, güvenlik, loglama, hız sınırlama
│   ├── db/               # SQLAlchemy asenkron motor, oturum yönetimi ve modeller
│   ├── engine/           # Saf Python kural motoru (tahta, torba, skorlama, kurallar)
│   │   └── locales/      # Dil paketleri (Türkçe ve İngilizce harf/puan tabloları)
│   ├── models/           # Veritabanı tabloları (User, Game, GamePlayer, Move, vb.)
│   ├── realtime/         # WebSocket bağlantı yöneticisi ve olay yayınlayıcı
│   ├── schemas/          # Pydantic v2 veri şemaları (istek, yanıt, hata modelleri)
│   └── services/         # İş mantığı servisleri (AuthService, GameService, TimeoutService)
├── data/
│   └── dictionaries/     # Bellek içi sözlük dosyaları (tr.txt, en.txt)
├── docs/                 # API dokümanları, yol haritası ve mimari rehberler
├── tests/                # Birim ve entegrasyon testleri
├── docker-compose.yml    # PostgreSQL konteyner tanımı
└── pyproject.toml        # Ruff, pytest ve proje ayarları
```

---

### 🚀 Hızlı Başlangıç

#### Ön Koşullar
- **Python 3.9+**
- **Docker ve Docker Compose** (veya OrbStack)

#### 1. Depoyu Klonlayın ve Sanal Ortamı Kurun
```bash
# Depoyu klonlayın
git clone https://github.com/your-username/word-puzzle-app.git
cd word-puzzle-app

# Sanal ortam oluşturun ve aktif edin
python3 -m venv .venv
source .venv/bin/activate

# Bağımlılıkları yükleyin
pip install -r requirements.txt
```

#### 2. Ortam Değişkenlerini Tanımlayın
Örnek yapılandırma dosyasını kopyalayın:
```bash
cp .env.example .env
```

#### 3. PostgreSQL Veritabanını Başlatın
```bash
docker compose up -d
```

#### 4. Veritabanı Şemasını Uygulayın (Migrasyon)
```bash
alembic upgrade head
```

#### 5. Geliştirme Sunucusunu Başlatın
```bash
fastapi dev app/main.py --port 8000
```
Sunucu `http://127.0.0.1:8000` adresinde çalışmaya başlayacaktır.

---

### 📚 API Dokümantasyonu

Sunucu çalışırken interaktif dokümantasyona tarayıcınızdan erişebilirsiniz:
- **Swagger UI:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc:** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- **OpenAPI Şeması:** [http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json)

Detaylı teknik dokümanlar için [`docs/api/`](docs/api/) dizinini inceleyebilirsiniz:
- [API Genel Bakış](docs/api/overview.md)
- [REST Uç Noktaları](docs/api/rest-endpoints.md)
- [WebSocket Rehberi](docs/api/websocket.md)
- [Hata Kodları Listesi](docs/api/errors.md)

---

### 🧪 Testleri ve Kontrolleri Çalıştırma

```bash
# Birim ve entegrasyon testlerini çalıştırın
pytest -v

# Kod formatı ve lint denetimi yapın
ruff check .
```
