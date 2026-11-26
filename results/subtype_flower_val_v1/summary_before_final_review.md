# 84 sınıflı Flower FedAvg — validation_v1

## Amaç ve gerçekleşen çalışma

`references/proposal.docx`, farklı saldırı dağılımlarına sahip istemcilerin ortak modelini yerel ve merkezi modellerle karşılaştırmayı; saldırıyı benign sayma ve doğru aile içinde yanlış alt tür seçme hatalarını ayırmayı hedefler. Bu deney, önerinin **84 sınıflı federe–merkezi karşılaştırmasını** gerçekleştirir. Bu görevde yeni yerel modeller, fiziksel istemciler veya dashboard uygulanmadı; önceki deneyler yeni ölçüm olarak sunulmadı.

## Veri ve eşdeğerlik kontrolleri

- Eğitim: `data/validation_v1/train.csv`, 22.450 kayıt; mevcut beş Non-IID istemci: 4.430 / 6.216 / 2.901 / 5.103 / 3.800. Birleşimlerinin sekiz metadata alanından oluşan benzersiz kayıt kimlikleri ve modele giren ön işlenmiş float32 tensörleri merkezi eğitimle birebir eşit. CSV okumada iki ham sayıda en fazla 4.136e-25 fark bulundu; model girdisine yansımadığı doğrulandı, veri değiştirilmedi.
- Değerlendirme yalnız `data/validation_v1/validation.csv`: 6.486 kayıt; 3.838 benign, 2.648 saldırı; 28 alt tür ve 7 aile. Web ailesi doğrulamada yok.
- Eğitimden türetilen benign + sıralı 83 saldırı sınıfı, 71 özellik ve alt tür→aile eşlemesi mevcut merkezi model ile birebir doğrulandı. Her alt tür tek aileye bağlı; doğrulama etiketleri de bu eşlemeyle uyumlu.
- Ön işleme: float64 giriş; NaN/±Inf→0; ±1e8 kırpma; sign(x)·log1p(abs(x)); float32. Eğitim/doğrulama tensörleri ve seed=42 başlangıç ağırlıkları orijinal kodla birebir eşit.
- `test_episode.csv` ve `test_web_diagnostic.csv` açılmadı; bu deneyin okuyucusu yalnız izin verilen eğitim/doğrulama dosyalarını kabul eder.

## Yapılandırma ve yürütme

Flower **1.40.0**, ayrı `flower_subtype_app/`, gerçek ClientApp/ServerApp, yerel SuperLink + Ray simülasyonu. Mimari: **71→64→32→84**, ReLU, 9.460 parametre. **15 tur**, her tur **5/5 istemci**, **1 yerel epoch**, batch **128**, Adam **0.001**, CPU; seed **42**, istemci karıştırma tohumu `42 + 100*tur + istemci_id`. Her tur Adam durumu yeniden başlatılır; merkezi modelin Adam durumu 15 epoch boyunca korunur. İki modelde toplam örnek sunumu 336.750; farklı optimizasyon yörüngeleri nedeniyle 15 tur, 15 merkezi epoch ile aynı güncelleme süreci değildir.

Her güncelleme gerçek örnek sayısıyla ağırlıklandırıldı: `n_i / 22450`. 75 istemci güncellemesi ve 15 turun tamamı denetlendi; Flower ağırlık ortalaması her tensörde bağımsız float64 referansla kontrol edildi. Değerlendirme yalnız son turda; doğrulama ile model seçimi yapılmadı.

Ölçülen strateji/eğitim süresi: **12.154 saniye** (SuperLink başlatma, paketleme ve son değerlendirme hariç). Bu simülasyon süresi fiziksel ağ gecikmesi veya Raspberry Pi performansı değildir.

Paketlenen Flower uygulaması `.flwr/apps` altında çalışsa bile veri yolu paket konumundan türetilmez: `project-root` ayarı kullanılır ve istemciye ConfigRecord ile gönderilir. Dataset FAB içine kopyalanmaz.

## Aynı doğrulama kümesindeki sonuçlar

Mevcut `models/subtype_centralized_val_v1.pt` yeniden değerlendirildi; tarihi JSON metrikleri ve 6.486 tahminin tamamı birebir yeniden üretildi. Merkezi model yeniden eğitilmedi.

| Ölçüt | Merkezi (%) | Flower FedAvg (%) | Fark (yüzde puan) |
|---|---:|---:|---:|
| Tam alt tür doğruluğu | 69.5498 | 63.7835 | -5.7663 |
| Alt tür Makro F1 (gözlenen 28) | 37.0299 | 9.6719 | -27.3580 |
| Yalnız saldırılarda tam alt tür doğruluğu | 26.0952 | 11.3671 | -14.7281 |
| Yalnız saldırılarda Makro F1 (27) | 35.0146 | 6.6475 | -28.3671 |
| Alt türden türetilen aile doğruluğu | 85.0910 | 76.9195 | -8.1714 |
| Aile Makro F1 (gözlenen 7) | 62.4807 | 33.5363 | -28.9444 |
| Saldırı tespit duyarlılığı | 76.5106 | 72.6964 | -3.8142 |
| Benign yanlış pozitif oranı | 0.4690 | 0.0521 | -0.4169 |

Ana alt tür Makro F1 yalnız ground-truth'ta gözlenen 28 sınıf üzerinden, saldırı Makro F1 27 saldırı sınıfından, aile Makro F1 7 gözlenen aileden hesaplandı; `zero_division=0`. Gözlenmeyen sınıflara tahminler örnek düzeyinde hata olarak sayılır; bu sınıfların F1 terimleri ana ortalamaya eklenmez. 84 satırlı sınıf raporundaki tüm-sınıflar Makro F1 ise farklı bir payda kullanır ve ana ölçüt değildir.

Sıfır destekli sınıfları da 0 sayan tüm-84 Makro F1: merkezi **0.123433**, FedAvg **0.032240**. Bu değer 84 sınıfın tamamının doğrulandığı anlamına gelmez.

## Hiyerarşik hata dökümü

| Ayrık kategori | Merkezi | Flower FedAvg |
|---|---:|---:|
| Tam doğru (benign dahil) | 4511 | 4137 |
| Doğru saldırı ailesi, yanlış alt tür | 1008 | 852 |
| Saldırı → benign | 622 | 723 |
| Benign → saldırı | 18 | 2 |
| Yanlış saldırı ailesi | 327 | 772 |
| **Toplam** | **6486** | **6486** |

Her örnek tam bir kategoriye girer. Tam-doğru sayısı / 6486 alt tür doğruluğunu; (tam-doğru + doğru-aile/yanlış-alt-tür) / 6486 aile doğruluğunu verir. Saldırı→benign / 2648 tespit kaçırma oranıdır; benign→saldırı / 3838 yanlış alarm oranıdır.

## Şekiller ve yeniden üretim

![Metrik karşılaştırması](subtype_flower_val_v1/comparison.png)

![Aile karışıklık matrisleri](subtype_flower_val_v1/family_confusion.png)

![Yerel eğitim kaybı](subtype_flower_val_v1/training_loss.png)

![Non-IID dağılım](subtype_flower_val_v1/client_distribution.png)

Alt tür karışıklık şekli `subtype_flower_val_v1/subtype_confusion_observed.png`: 28 gözlenen gerçek sınıf × 84 tahmin sınıfı; tam 84×84 sayımlar CSV'de. Şekiller ayrıca SVG olarak saklandı.

```bash
/home/seniorfl/seniorproject-fl-venv/bin/python scripts/26_run_flower_subtype_val_v1.py --stage all
```

Yeni çalıştırmada mevcut deney çıktıları kasıtlı olarak korunur; bağımsız tekrar için yeni çıktı/model adları ve yeni yedek manifesti gerekir. Sadece doğrulamak için `--stage verify` kullanılabilir. Tam bağımlılıklar `requirements.freeze.txt`, ayarlar `config.json`, ortam `environment.json`, giriş SHA-256'ları `data_audit.json`, kaynak yedeği `backup.json`, tamamlanan deneyin kaynak kopyası `experiment_source.tar.gz`, komut ve log `launch.json` / `simulation.log` dosyalarındadır.

Model: `models/subtype_flower_val_v1.pt`. `results/subtype_flower_val_v1/` içinde iki model için JSON metrikler, tahminler, 84×84 alt tür ve 8×8 aile matrisleri, sınıf/aile raporları, hiyerarşik dökümler, `rounds.csv` (15), `client_rounds.csv` (75), `comparison.csv`, sınıf kapsamı ve bütünlük manifestleri saklanır. `verification.json` son tutarlılık ve korunma kontrollerini kaydeder.

## Yorum ve sınırlılıklar

Bu tek koşuda FedAvg'nin alt tür doğruluğu merkeziden -5.7663 yüzde puan, saldırı alt tür doğruluğu -14.7281 yüzde puan, aile doğruluğu -8.1714 yüzde puan farklıdır. Benign çoğunluğu nedeniyle genel doğruluk, saldırı alt tür başarısıyla birlikte okunmalıdır; güvenilirlik için birden çok tohum ve istemci dağılımı gerekir.

- Episode ID'leri sezgisel aday gruplardır; eğitim/doğrulama saldırı episode kesişiminin sıfır olması bağımsız oturum garantisi vermez. Tam bağımsız oturum değerlendirmesi iddia edilmez.
- Benign doğrulama zamansal holdout'tur; bağımsız benign episode ayrımı değildir.
- **56/84 sınıf doğrulamada yoktur**; web ailesinin performansı ölçülmedi. 84 çıkışlı model, tam 84 sınıflı doğrulama kapsamı demek değildir.
- Tek tohum, tek Non-IID bölüşüm ve sabit tam katılım kullanıldı; anlamlılık, güven aralığı veya genellenebilir üstünlük gösterilmedi. Yerel eğitimde görülmeyen saldırılara transfer, yeni yerel 84-sınıf modellerle aynı doğrulama üzerinde karşılaştırılmadan kanıtlanamaz.
- Önceki yerel/8-sınıflı deneyler bu tablodaki 84-sınıflı sonuçlarla doğrudan eşdeğer kabul edilmez. Gerçek istemci gecikmesi, enerji tüketimi, iletişim maliyeti ve saldırı testbed'i bu çalışmada ölçülmedi.

## Gelecek çalışma

Aynı protokolde yerel 84-sınıf modelleri, istemcide görülmeyen sınıf analizi, çoklu tohum/dağılım ve kısmi katılım deneyleri; gerçek Raspberry Pi Flower istemcileri; izole Kali Linux IIoT saldırı testbed'inde kontrollü trafik değerlendirmesi; dashboard ve donanım çıkarım ölçümleri planlanmaktadır. Fiziksel testbed bu görevde uygulanmadı.

API dayanağı: [Flower resmi ClientApp/ServerApp örneği](https://flower.ai/docs/framework/tutorial-series-get-started-with-flower-pytorch.html); kurulu 1.40.0 API imzaları ayrıca doğrudan kontrol edildi. Sayısal deney sonuçları yerel çalıştırmadan üretilmiştir.
