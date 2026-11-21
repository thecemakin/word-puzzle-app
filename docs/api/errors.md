# Hata Sözlüğü (`docs/api/errors.md`)

Tüm API hataları istemcinin `User.ui_language` tercihine göre yerelleştirebilmesi için standart `ErrorResponse` formatında döner:

```json
{
  "error_code": "INVALID_WORD",
  "message": "Invalid word(s): XYZ",
  "details": {
    "invalid_words": ["XYZ"]
  }
}
```

---

## Sistem & Doğrulama Hataları

| HTTP | `error_code` | Açıklama |
| --- | --- | --- |
| 422 | `VALIDATION_ERROR` | Pydantic istek şeması doğrulama hatası (`details.errors`) |
| 429 | `RATE_LIMIT_EXCEEDED` | Auth uçlarında hız sınırı aşıldı (`details.retry_after_seconds`) |

---

## Kimlik Doğrulama & Kullanıcı Hataları

| HTTP | `error_code` | Açıklama |
| --- | --- | --- |
| 400 | `UNSUPPORTED_UI_LANGUAGE` | Desteklenmeyen `ui_language` değeri |
| 401 | `AUTHENTICATION_REQUIRED` | `Authorization: Bearer` başlığı eksik |
| 401 | `INVALID_TOKEN` | Geçersiz JWT veya eksik `sub`/`jti` |
| 401 | `TOKEN_EXPIRED` | Token süresi dolmuş |
| 401 | `INVALID_TOKEN_TYPE` | Beklenen token tipi (`access`/`refresh`) uyuşmuyor |
| 401 | `TOKEN_REVOKED` | Refresh token iptal edilmiş veya daha önce kullanılmış |
| 401 | `INVALID_CREDENTIALS` | Kullanıcı adı/e-posta veya parola hatalı |
| 401 | `USER_NOT_FOUND` | Token sahibi kullanıcı bulunamadı veya pasif |
| 403 | `USER_INACTIVE` | Kullanıcı hesabı pasif |
| 409 | `USERNAME_ALREADY_EXISTS` | Kullanıcı adı (büyük/küçük harf duyarsız) zaten kayıtlı |
| 409 | `EMAIL_ALREADY_EXISTS` | E-posta adresi zaten kayıtlı |

---

## Oyun & Eşleştirme Hataları

| HTTP | `error_code` | Açıklama |
| --- | --- | --- |
| 400 | `UNSUPPORTED_LANGUAGE` | Desteklenmeyen veya aktif olmayan oyun dili |
| 400 | `INVALID_TURN_DURATION` | İzinli süre seçenekleri (`12, 24, 48, 72`) dışında değer |
| 400 | `CANNOT_PLAY_SELF` | Kullanıcı kendisini oyuna davet edemez |
| 403 | `NOT_A_GAME_PARTICIPANT` | Kullanıcı bu oyunun katılımcısı veya davetlisi değil |
| 403 | `GAME_INVITE_ONLY` | Oyun yalnızca davet edilen kullanıcıya açık |
| 404 | `GAME_NOT_FOUND` | Oyun bulunamadı |
| 404 | `OPPONENT_NOT_FOUND` | Davet edilen kullanıcı bulunamadı |
| 409 | `GAME_NOT_JOINABLE` | Oyun artık `waiting` durumunda değil |
| 409 | `ALREADY_IN_GAME` | Kullanıcı zaten bu oyunda |
| 409 | `GAME_FULL` | Oyunda zaten 2 oyuncu var |
| 409 | `GAME_NOT_ACTIVE` | Hamle yalnızca `active` oyunda yapılabilir |
| 409 | `VERSION_CONFLICT` | `expected_version` güncel oyun sürümüyle uyuşmuyor |
| 409 | `GAME_EXPIRED` | Sıra süresi doldu (oyun anında `TIMEOUT` olarak kapatılır) |
| 409 | `OPPONENT_MISSING` | Oyunda 2 oyuncu yok |
| 409 | `NOT_YOUR_TURN` | Hamle sırası bu kullanıcıda değil |

---

## Oyun Motoru Hataları (HTTP 400)

| `error_code` | Açıklama |
| --- | --- |
| `EMPTY_PLACEMENT` | En az 1 taş yerleştirilmelidir |
| `OUT_OF_BOUNDS` | Koordinat `0..14` tahta sınırları dışında |
| `DUPLICATE_COORDINATE` | Aynı kareye birden fazla taş koyuldu |
| `CELL_OCCUPIED` | Hedef kare zaten dolu |
| `INVALID_LETTER` | Harf oyunun dili (`Game.language`) için geçerli değil |
| `NOT_ALIGNED` | Taşlar tek satır veya tek sütunda hizalanmalıdır |
| `FIRST_MOVE_MUST_COVER_CENTER` | İlk hamle merkez kareden `(7, 7)` geçmelidir |
| `WORD_TOO_SHORT` | Oluşan kelime en az 2 harfli olmalıdır |
| `GAP_IN_PLACEMENT` | Yerleştirilen taşlar arasında boş kare olamaz |
| `NOT_CONNECTED` | Yeni taşlar mevcut taşlara temas etmelidir |
| `TILES_NOT_IN_RACK` | Oyuncunun elinde gerekli taşlar yok (`details.missing_tiles`) |
| `INVALID_WORD` | Sözlükte bulunmayan kelime(ler) (`details.invalid_words`) |
| `INVALID_SWAP` | Değiştirmek için en az 1 taş seçilmelidir |
| `INSUFFICIENT_BAG_TILES` | Torbada değişim için yeterli taş yok |
| `DICTIONARY_NOT_LOADED` | İlgili dil sözlüğü belleğe yüklenmemiş |
