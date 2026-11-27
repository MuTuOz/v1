# Kali Linux'u nereye kurmalı — VMware ve alternatifler

Arkadaşınız kendi PC'sindeki VMware'e kuracaksa aşağıdaki **Seçenek A**'yı izleyin. En kritik nokta
ağ ayarıdır: Kali, Pi ile **aynı fiziksel/Wi-Fi ağında** bir IP almalı — bu yüzden VMware'de
**Bridged**, asla **NAT** kullanmayın.

## Gereksinimler (her seçenek için)

* En az 2 çekirdek, 4 GB RAM (8 GB rahat), 40+ GB disk.
* VMware Workstation Pro/Player (Windows) ya da VMware Fusion (Mac) kurulu olmalı.

## Seçenek A — VMware'e Kali kurulumu (önerilen, arkadaşınızın durumu)

1. **İndirin:** https://www.kali.org/get-kali/#kali-virtual-machines adresinden **VMware** sekmesinden
   `.7z` dosyasını indirin (hazır sanal makine imajı; ISO'dan kurulumdan çok daha hızlı).
2. **Açın:** `.7z`'yi açın, içindeki `.vmx` dosyasına VMware'de çift tıklayın veya
   "Open a Virtual Machine" ile seçin.
3. **Ağ ayarı (en önemli adım):** VM ayarlarından (Edit virtual machine settings → Network Adapter)
   modu **Bridged** yapın, "Replicate physical network connection state" işaretli kalsın.
   * **NAT kullanmayın** — NAT modunda Kali, host'un arkasında ayrı bir özel ağda kalır ve Pi'yi
     (ya da Pi, Kali'yi) göremez.
   * Host'un hangi fiziksel arayüzden Wi-Fi'ya bağlı olduğunu kontrol edin; Bridged adapter o
     arayüzü kullanmalı (VMware genelde otomatik seçer, "Automatic" bırakmak genelde yeterli).
   * **Promiscuous mode:** ARP spoofing (`mitm_arp-spoofing`) ve paket yakalama (`tcpdump`) için
     sanal anahtarın promiscuous mode'a izin vermesi gerekir. VMware Workstation/Player'da bu
     genelde varsayılan olarak açıktır; VMware'in kurumsal/ESXi sürümlerinde ayrıca switch
     ayarından "Promiscuous Mode: Accept" açılması gerekebilir.
4. **Giriş:** varsayılan kullanıcı `kali` / şifre `kali` (ilk girişte değiştirin: `passwd`).
5. **Güncelleyin ve gerekli araçları kurun:**
   ```bash
   sudo apt update && sudo apt full-upgrade -y
   sudo apt install -y nmap hping3 hydra ettercap-text-only dsniff slowhttptest sqlmap mosquitto-clients tcpdump git
   ```
6. **IP'yi doğrulayın:** `ip addr` ile Kali'nin Pi ile aynı alt ağda (ör. `192.168.1.x`) bir IP
   aldığını kontrol edin. `ping <Pi'nin IP'si>` ile erişimi test edin.
7. **Repoyu çekin:**
   ```bash
   git clone <bu reponun URL'si> ~/seniorproject-v1
   cd ~/seniorproject-v1/kali_lab
   ```
8. Buradan sonrası `kali_lab/README.md`'deki adımlarla aynı (dry-run önce, sonra gerçek çalıştırma).

### VMware Fusion / Player farkları
Adımlar aynı; sadece ağ ayarının adı Fusion'da "Bridged Networking", Player'da "Bridged" olarak
geçer. Workstation Pro'da birden fazla bridged arayüz varsa (Ethernet + Wi-Fi), Virtual Network
Editor'den doğru fiziksel arayüzü seçtiğinizden emin olun.

## Alternatifler (VMware mümkün değilse)

| Seçenek | Ne zaman tercih edilir | Not |
|---|---|---|
| **VirtualBox + Kali OVA** | VMware lisansı/kurulumu sorun çıkarırsa | https://www.kali.org/get-kali/#kali-virtual-machines sayfasında VirtualBox imajı da var; ağ modu "Bridged Adapter" olmalı, aynı mantık |
| **Bare-metal / Live USB** | En gerçekçi performans, VM ağ karmaşıklığı istenmiyorsa | Resmi ISO + `dd`/Rufus ile USB'ye yazılır; donanıma doğrudan kurulum kalıcı, Live mod geçicidir |
| **WSL2 (Windows)** | Hızlı pratik, ayrı makine/VM istemiyorsanız | **Önerilmez burada**: `arpspoof`, raw socket gerektiren `hping3` floodları ve promiscuous capture WSL2'nin sanal ağ katmanında güvenilir çalışmaz; sadece `nmap`/`hydra` gibi araçlar için uygun olabilir |
| **Docker container (host ağıyla)** | Hızlı tek komutla ortam | `docker run --rm -it --network host --cap-add=NET_ADMIN --cap-add=NET_RAW kalilinux/kali-rolling bash` ile network-level araçlar çalışabilir, ama `--network host` Linux host gerektirir (Windows/Mac Docker Desktop'ta host ağı farklı davranır); VM kadar izole/temiz değil |
| **Ayrı fiziksel bir laptop'a kurulum** | Elinizde boşta bir cihaz varsa | En temiz izolasyon; `kali_lab_deployment_plan.md`'deki adreslemeyi uygulamak daha kolay |

VMware zaten mevcutsa Seçenek A'yı kullanın; en az sürtünme ve projenin geri kalanıyla (script 36,
`docs/pc_server_pi_client_quickstart_tr.md`) tutarlı bir ağ modeli veriyor.

## Son kontrol

Kali açıldıktan ve ağ doğrulandıktan sonra `kali_lab/attack_orchestrator.py --dry-run` ile önce
komutları gözden geçirin — `kali_lab/README.md`'deki örnek komutu kullanabilirsiniz. Gerçek
çalıştırmadan önce hedefin (Pi'nin) IP'sinin doğru olduğundan ve ağın izole/kontrollü olduğundan
emin olun (`docs/kali_lab_deployment_plan.md`).
