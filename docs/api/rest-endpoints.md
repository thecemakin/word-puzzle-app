# REST Uç Noktaları ve Örnek Akış (`docs/api/rest-endpoints.md`)

## Auth (`/api/v1/auth`)
- `POST /api/v1/auth/register` — Yeni hesap (`201`)
- `POST /api/v1/auth/login` — `access_token` & `refresh_token` (`200`)
- `POST /api/v1/auth/refresh` — Refresh token rotation (`200`)
- `POST /api/v1/auth/logout` — Refresh token iptali (`204`)

## Kullanıcılar (`/api/v1/users`)
- `GET /api/v1/users/me` — Profil ve `ui_language`
- `PATCH /api/v1/users/me` — `ui_language` (`"tr"` / `"en"`) güncelleme

## Oyunlar (`/api/v1/games`)
- `GET /api/v1/games/options` — Desteklenen oyun dilleri ve süreler (`[12, 24, 48, 72]`)
- `POST /api/v1/games` — Yeni oyun oluştur (`language`, `turn_duration_hours`, opsiyonel `opponent_username`)
- `POST /api/v1/games/matchmaking` — Aynı dil + sürede açık oyunla eşleş veya yeni açık oyun aç (`matched: bool`)
- `GET /api/v1/games?status=active&limit=20&offset=0` — Kullanıcının oyunları (sayfalı)
- `GET /api/v1/games/{game_id}` — Oyun durumu (rakibin `rack` alanı anti-cheat gereği `null` döner)
- `POST /api/v1/games/{game_id}/join` — Bekleyen oyuna katıl ve 7'şer taş dağıt
- `POST /api/v1/games/{game_id}/moves` — Hamle gönder (`PLAY`, `PASS`, `SWAP`, `RESIGN`)
- `GET /api/v1/games/{game_id}/moves?since_move_number=0&limit=100` — Hamle geçmişi ve yeniden bağlanma senkronizasyonu

---

## Örnek Hamle İsteği (`PLAY`)

```json
{
  "move_type": "PLAY",
  "expected_version": 2,
  "placements": [
    {"row": 7, "col": 6, "letter": "E", "is_blank": false},
    {"row": 7, "col": 7, "letter": "L", "is_blank": false},
    {"row": 7, "col": 8, "letter": "M", "is_blank": false},
    {"row": 7, "col": 9, "letter": "A", "is_blank": false}
  ],
  "tiles_to_swap": []
}
```
