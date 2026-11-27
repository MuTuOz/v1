# Commands executed — pi_lan_1client_r3_s42 (2026-11-26, UTC ~13:51–14:07)

PC (WSL2, `/mnt/c/Users/murat/OneDrive/Desktop/Ders/CS401/SeniorProject/SeniorProject/without_data/v1`, venv `/home/mozen/seniorproject-fl-venv`):
```
python scripts/36_pc_pi_federation.py certs --server-ip 10.96.27.14
python scripts/36_pc_pi_federation.py prepare --experiment-id pi_lan_1client_r3_s42 --num-clients 1 --rounds 3 --partition-note balanced
FLWR_HOME=results/pi_fl_v1/pi_lan_1client_r3_s42/flwr_home flower-superlink --host 0.0.0.0 --port 9092 --ssl-ca-certfile /home/mozen/.seniorfl_pki/pi_fl_v1/ca.pem --ssl-certfile /home/mozen/.seniorfl_pki/pi_fl_v1/server.pem --ssl-keyfile /home/mozen/.seniorfl_pki/pi_fl_v1/server.key --disable-runtime-dependency-installation --database results/pi_fl_v1/pi_lan_1client_r3_s42/superlink_state.db
FLWR_HOME=results/pi_fl_v1/pi_lan_1client_r3_s42/flwr_home flwr run hardware_deployment/app pilab --run-config results/pi_fl_v1/pi_lan_1client_r3_s42/run_config.toml --stream
python scripts/36_pc_pi_federation.py verify --experiment-id pi_lan_1client_r3_s42
python scripts/37_pi_fl_round_timing.py --experiment-id pi_lan_1client_r3_s42
```
Pi (`iari@10.96.27.10`, venv `~/seniorfl-venv`, PATH includes venv bin; attempts 1–2 failed, see device_2_pi/FAILED_*):
```
flower-supernode --superlink 10.96.27.14:9092 --root-certificates ~/seniorfl/pki/ca.pem --host 127.0.0.1 --port 9094 --node-config 'client-id=2 data-path="/home/iari/seniorfl/data/client_2_train.csv" log-dir="/home/iari/seniorfl/pi_fl_logs/pi_lan_1client_r3_s42"'
```
wlan0 rx/tx counters were read over SSH before and after `flwr run`; Pi logs copied with scp into device_2_pi/.
