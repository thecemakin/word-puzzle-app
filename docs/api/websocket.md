# WebSocket Sözleşmesi (`docs/api/websocket.md`)

## Bağlantı
- **URL:** `WS /api/v1/games/{game_id}/ws?token=<access_jwt>` (veya `Authorization: Bearer <access_jwt>`)
- **Mesaj Boyutu Limiti:** Maksimum `1024` byte (`ping` canlı tutma mesajları için)

### Kapatma Kodları
| Kod | Anlamı |
| --- | --- |
| `4401` | Token eksik, geçersiz, süresi dolmuş veya kullanıcı pasif |
| `4403` | Kullanıcı bu oyunun katılımcısı değil |
| `4404` | Oyun bulunamadı |
| `1009` | Gelen WebSocket mesajı 1024 byte sınırını aştı |

---

## İstemci → Sunucu
- Metin `"ping"` → Sunucu `{"event": "pong"}` döner.

---

## Sunucu → İstemci Olayları

> **Anti-Cheat:** Hiçbir WebSocket olayında oyuncuların `rack` taşları veya `tile_bag` içeriği yer almaz.

### 1. `connected`
Bağlantı açıldığında yalnızca bağlanan istemciye gönderilir:
```json
{
  "event": "connected",
  "game_id": "uuid",
  "status": "active",
  "version": 2,
  "move_count": 0
}
```

### 2. `game_started`
İkinci oyuncu katıldığında (`join` veya `matchmaking`) yayınlanır:
```json
{
  "event": "game_started",
  "game_id": "uuid",
  "language": "tr",
  "current_turn_user_id": "uuid",
  "turn_expires_at": "2026-11-22T12:00:00+00:00",
  "bag_remaining": 86,
  "version": 2,
  "players": [
    {"user_id": "uuid", "username": "p1", "seat_order": 1, "score": 0, "rack_count": 7}
  ]
}
```

### 3. `move_made`
Her `PLAY`, `PASS`, `SWAP`, `RESIGN` hamlesinden sonra yayınlanır:
```json
{
  "event": "move_made",
  "game_id": "uuid",
  "move_number": 1,
  "move_type": "PLAY",
  "user_id": "uuid",
  "placements": [{"row": 7, "col": 6, "letter": "E", "is_blank": false}],
  "words_formed": [{"word": "ELMA", "score": 10}],
  "score_gained": 10,
  "current_turn_user_id": "uuid",
  "turn_expires_at": "2026-11-22T12:00:00+00:00",
  "bag_remaining": 82,
  "status": "active",
  "version": 3,
  "players": [...]
}
```

### 4. `turn_expired` & `game_finished`
Süre aşımı (`TIMEOUT`) veya oyun bitişinde yayınlanır:
```json
{
  "event": "game_finished",
  "game_id": "uuid",
  "finish_reason": "TIMEOUT",
  "winner_id": "uuid",
  "version": 4,
  "players": [...]
}
```
