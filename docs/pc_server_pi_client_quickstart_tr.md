# PC = sunucu, Raspberry Pi = istemci — hızlı başlangıç (Flower 1.40.0)

Hocanın sorusu: *"Pi ile çalışıyor mu? PC server, Pi client olacak şekilde."*

**Durum (2026-11-26):** Yazılım yolu, Pi'nin kullanacağı komutların aynısıyla tek bir x86 makinede
doğrulandı (TLS, sunucu `0.0.0.0:9092`, istemciler loopback olmayan IP üzerinden, sertifika SAN = IP;
3 tur, 6 güncelleme, FedAvg ağırlıkları kontrol edildi — bkz. `results/pi_fl_v1/lanip_check_2clients_r3_s42/`).
**Güncelleme (2026-11-26, aynı gün): gerçek bir Raspberry Pi 5 üzerinde çalıştırıldı ve doğrulandı** —
PC (WSL2, mirrored ağ) SuperLink, Pi 5 SuperNode; 1 istemcili 3 tur ve PC+Pi 2 istemcili 5 tur, ikisinde de
`verify` geçti ve Pi'nin kendi JSON'ları `aarch64` gösteriyor. Kanıt ve sınırlamalar:
[`results/pi_fl_v1/PHYSICAL_PI_RUNS_2026-11-26.md`](../results/pi_fl_v1/PHYSICAL_PI_RUNS_2026-11-26.md).
Bu sırada bulunan ek tuzaklar aşağıdaki "Sık hatalar" tablosunun sonuna eklendi.

Yardımcı betik: [`scripts/36_pc_pi_federation.py`](../scripts/36_pc_pi_federation.py). Uygulama kodu:
`hardware_deployment/app` (sunucu FAB'ı SuperNode'lara kendisi gönderir; Pi'ye proje klonlamak gerekmez,
sadece Python paketleri + kendi eğitim CSV'si + `ca.pem` yeterli).

## 0. Gerekenler

| | PC (sunucu) | Raspberry Pi (istemci) |
|---|---|---|
| OS | Linux / WSL2 | **64-bit** Raspberry Pi OS (Bookworm), Pi 4 (≥4 GB) veya Pi 5 |
| Python | 3.12 (proje venv'i) | 3.11–3.13 |
| Paketler | mevcut venv | `pip install "flwr==1.40.0" torch numpy pandas psutil` (aarch64 torch PyPI'da CPU wheel olarak var) |
| Veri | — | sadece o istemcinin **eğitim** CSV'si (`client_N_train.csv`); validation/test asla |

İlk deneme için repodaki eğitim-only dosyalar kullanılabilir:
`results/pre_pi_research_v1/audit/allocations/balanced/client_1_train.csv` (~2.4 MB) → Pi'ye `scp` ile.

## 1. Ağ (en sık takılınan yer)

1. PC ve Pi aynı izole lab ağında olsun (internet'e açık değil). PC'nin IP'sini bul: Linux `hostname -I`, Windows `ipconfig`.
2. **WSL2 kullanıyorsanız** (proje venv'i WSL2'de): WSL2 varsayılan NAT modunda Pi, WSL içindeki
   9092 portuna doğrudan ulaşamaz. İki seçenek (Windows tarafında, yönetici yetkisiyle sizin yapmanız gerekir):
   * `%UserProfile%\.wslconfig` içine `[wsl2]` altında `networkingMode=mirrored` yazıp `wsl --shutdown`, ya da
   * `netsh interface portproxy add v4tov4 listenport=9092 listenaddress=0.0.0.0 connectport=9092 connectaddress=<WSL_IP>`
   * Her iki durumda Windows Defender Firewall'da TCP 9092 için **yalnızca lab alt ağına** gelen kural.
3. Pi'den test: `nc -vz <PC_IP> 9092` (SuperLink çalışırken "succeeded" görmelisiniz).
4. Pi'de `HTTPS_PROXY` tanımlıysa `NO_PROXY=<PC_IP>` ekleyin (bu oturumdaki ilk LAN-IP denemesi tam olarak bu yüzden başarısız oldu).

> Flower 1.40'ta Fleet + Control + Runtime API'leri **tek HTTPS portunda** çalışır (`--host/--port`,
> varsayılan `127.0.0.1:8000`). Eski `--fleet-api-address` bayrakları yok sayılır — ilk denememiz bu
> yüzden başarısız oldu. Betik `--host 0.0.0.0 --port 9092` kullanır.

## 2. PC'de bir kerelik hazırlık

```bash
python scripts/36_pc_pi_federation.py certs --server-ip <PC_IP>
```
Anahtarlar repo **dışına** yazılır (`~/.seniorfl_pki/pi_fl_v1/`). Pi'ye sadece `ca.pem` kopyalanır; `*.key` asla.

```bash
python scripts/36_pc_pi_federation.py prepare --experiment-id pi_lan_2clients_r5_s42 --num-clients 2 --rounds 5
```
```bash
python scripts/36_pc_pi_federation.py commands --experiment-id pi_lan_2clients_r5_s42 --server-ip <PC_IP>
```
Son komut PC ve her istemci için çalıştırılacak tam komutları ve `flwr` profil dosyasını yazdırır.

## 3. Çalıştırma sırası

1. **PC, terminal 1:** yazdırılan `flower-superlink ...` komutu.
2. **Pi (istemci 2):** yazdırılan `flower-supernode --superlink <PC_IP>:9092 --root-certificates ca.pem ... --node-config "client-id=2 data-path=... log-dir=..."`.
   İkinci istemci PC'nin kendisi olabilir (istemci 1, `--superlink 127.0.0.1:9092`, farklı `--port`), ya da
   ikinci bir Pi. Sadece tek Pi ile denemek için `prepare --num-clients 1`.
3. **PC, terminal 2:** `flwr` profilini (`$FLWR_HOME/config.toml`) yazdıktan sonra `flwr run hardware_deployment/app pilab --run-config results/pi_fl_v1/<id>/run_config.toml --stream`.
4. Bittiğinde: `python scripts/36_pc_pi_federation.py verify --experiment-id <id>`.
5. Pi'deki `log-dir` klasörünü (her tur için JSON: eğitim süresi, RSS, 10 çıkarım zamanlaması, platform)
   PC'ye kopyalayıp aynı deney klasörüne `device_2_pi/` olarak koyun. **Pi kanıtı budur.**
6. Ekran görüntüsü: Pi terminalinde SuperNode çıktısı + `cat /proc/device-tree/model`; tarih ve deney
   ID'si ile `results/pi_fl_v1/<id>/screenshots/` altına. Metrikler ekran görüntüsünden değil JSON/CSV'den alınır.
7. Pi'de çıkarım performansı için repoyu Pi'ye klonlayın (`models/` ve gerekli `results/` dosyaları repoda) ve
   aynı benchmark'ı çalıştırın: `python scripts/35_performance_benchmark.py --device-label pi4_arm64`
   (PC'de de `--device-label pc_x86` ile). Sonuç `results/performance_v1/<etiket>_<zaman>/` altına yazılır.

## 4. Güvenlik notları

* TLS sunucu doğrulaması var; SuperNode kimlik doğrulaması (`--enable-supernode-auth`) bu kurulumda
  **kapalı**: lab ağına giren herhangi bir cihaz istemci olarak bağlanabilir. Ağı izole tutun; gerekirse
  Flower'ın node-auth rehberine göre anahtarları ekleyin. Bu mTLS veya secure aggregation değildir.
* Control API de aynı porttan açılır; portu yalnızca lab alt ağına açın.

## 5. Sık hatalar

| Belirti | Sebep / çözüm |
|---|---|
| SuperNode: `Connection attempt failed, retrying` sonsuz | port yanlış, WSL2 NAT, firewall, proxy env; `nc -vz` ile test |
| `certificate verify failed` / hostname mismatch | sertifika SAN'ında PC IP'si yok → `certs --server-ip <doğru IP>` ile yeniden üret |
| `Clients unavailable` (120 s) | `num_clients` kadar SuperNode bağlanmadı |
| `Client schema fingerprint mismatch` | istemcideki uygulama farklı sürüm; aynı FAB'ı kullanın (Flower kendi dağıtır) |
| `Training size changed within run` | çalıştırma sırasında CSV değişti |
| Pi'de torch import hatası | 32-bit OS veya uyumsuz Python; 64-bit OS + `pip install torch` |
| Pi'de `pip install torch` GB'larca `nvidia-*` indiriyor | aarch64 PyPI wheel'i CUDA bağımlılıkları çekiyor; `pip install --index-url https://download.pytorch.org/whl/cpu torch` kullanın |
| SuperNode: `FileNotFoundError: 'flower-superexec'` | venv `bin` PATH'te değil; `export PATH=~/seniorfl-venv/bin:$PATH` sonra başlatın |
| SuperNode: `Runtime HTTP API failed to start` | önceki SuperNode süreci 9094'ü tutuyor; `pgrep -af flower-supernode` ile bulup kapatın |
| Pi'den 9092'ye `bash -c "</dev/tcp/<PC_IP>/9092"` başarısız (WSL2 mirrored) | Windows Firewall **ve** Hyper-V firewall gelen kuralı gerekir (`New-NetFirewallRule` + `New-NetFirewallHyperVRule -VMCreatorId '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}'`, yalnızca lab alt ağı; yönetici) |
