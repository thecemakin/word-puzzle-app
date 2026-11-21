# API Genel Bakış (`docs/api/overview.md`)

- **Base Prefix:** `/api/v1`
- **Geliştirme Dokümantasyonu (Swagger / ReDoc):**
  - `GET /docs` (Swagger UI — `APP_ENV=production` iken kapalıdır)
  - `GET /redoc` (ReDoc — `APP_ENV=production` iken kapalıdır)
  - `GET /openapi.json` (OpenAPI 3.x şeması)
- **Sistem Uç Noktaları:**
  - `GET /` — Uygulama adı, ortam ve çalışma durumu
  - `GET /health` — Veritabanı bağlantısı dahil sağlık kontrolü (`200 ok` / `503 degraded`)

---

## Kimlik Doğrulama (JWT Bearer)
1. `POST /api/v1/auth/register` ile kullanıcı oluşturun.
2. `POST /api/v1/auth/login` ile `access_token` + `refresh_token` alın.
3. Korumalı tüm REST isteklerinde `Authorization: Bearer <access_token>` başlığını gönderin.
4. `access_token` süresi dolduğunda `POST /api/v1/auth/refresh` ile yeni token çifti alın (eski refresh token otomatik iptal edilir; tekrar kullanılırsa güvenlik amacıyla tüm oturumlar kapatılır).

---

## Dil Ayrımı
- **`User.ui_language`:** Kullanıcının kendi uygulama arayüzü ve bildirim dili (`tr`, `en`). `PATCH /api/v1/users/me` ile güncellenebilir.
- **`Game.language`:** Oyun kurulurken seçilen kelime sözlüğü, harf havuzu ve puanlama dili (`tr`, `en`). Oyun boyunca **değiştirilemez**.

---

## İstek Takibi
Her HTTP yanıtında `X-Request-ID` başlığı döner. İstemci tarafından gönderilen `X-Request-ID` değeri korunarak loglara yazılır.
