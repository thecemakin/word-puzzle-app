# Sözlük Dosyaları (`data/dictionaries/`)

Her oyun dili için UTF-8 kodlamalı, satır başına tek kelime içeren bir `.txt` dosyası bulunur (`tr.txt`, `en.txt` vb.).

- Boş satırlar ve `#` ile başlayan yorum satırları yükleme sırasında yok sayılır.
- Kelimeler ilgili dilin `LanguagePack.normalize()` kuralına göre otomatik büyük harfe dönüştürülür (Türkçe için `i -> İ`, `ı -> I` dahil).
- Üretim ortamında bu başlangıç dosyalarının yerine tam sözlük listeleri (ör. TDK tabanlı Türkçe liste, TWL/SOWPODS İngilizce liste) doğrudan yerleştirilebilir.
- Yeni bir dil eklemek için `app/engine/locales/` altında yeni bir `LanguagePack` tanımlayıp kaydetmek ve buraya `<kod>.txt` dosyasını koymak yeterlidir.
