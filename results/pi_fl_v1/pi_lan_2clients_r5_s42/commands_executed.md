# Commands executed — pi_lan_2clients_r5_s42 (2026-11-26, UTC ~14:08–14:10)

PC (WSL2, `/mnt/c/Users/murat/OneDrive/Desktop/Ders/CS401/SeniorProject/SeniorProject/without_data/v1`, venv `/home/mozen/seniorproject-fl-venv`), same certificates as pi_lan_1client_r3_s42:
```
python scripts/36_pc_pi_federation.py prepare --experiment-id pi_lan_2clients_r5_s42 --num-clients 2 --rounds 5 --partition-note balanced
FLWR_HOME=results/pi_fl_v1/pi_lan_2clients_r5_s42/flwr_home flower-superlink --host 0.0.0.0 --port 9092 --ssl-ca-certfile /home/mozen/.seniorfl_pki/pi_fl_v1/ca.pem --ssl-certfile /home/mozen/.seniorfl_pki/pi_fl_v1/server.pem --ssl-keyfile /home/mozen/.seniorfl_pki/pi_fl_v1/server.key --disable-runtime-dependency-installation --database results/pi_fl_v1/pi_lan_2clients_r5_s42/superlink_state.db
flower-supernode --superlink 127.0.0.1:9092 --root-certificates /home/mozen/.seniorfl_pki/pi_fl_v1/ca.pem --host 127.0.0.1 --port 9095 --node-config 'client-id=1 data-path="/mnt/c/Users/murat/OneDrive/Desktop/Ders/CS401/SeniorProject/SeniorProject/without_data/v1/results/pre_pi_research_v1/audit/allocations/balanced/client_1_train.csv" log-dir="/mnt/c/Users/murat/OneDrive/Desktop/Ders/CS401/SeniorProject/SeniorProject/without_data/v1/results/pi_fl_v1/pi_lan_2clients_r5_s42/device_1_pc"'
FLWR_HOME=results/pi_fl_v1/pi_lan_2clients_r5_s42/flwr_home flwr run hardware_deployment/app pilab --run-config results/pi_fl_v1/pi_lan_2clients_r5_s42/run_config.toml --stream
python scripts/36_pc_pi_federation.py verify --experiment-id pi_lan_2clients_r5_s42
python scripts/37_pi_fl_round_timing.py --experiment-id pi_lan_2clients_r5_s42
```
Pi (`iari@10.96.27.10`):
```
flower-supernode --superlink 10.96.27.14:9092 --root-certificates ~/seniorfl/pki/ca.pem --host 127.0.0.1 --port 9094 --node-config 'client-id=2 data-path="/home/iari/seniorfl/data/client_2_train.csv" log-dir="/home/iari/seniorfl/pi_fl_logs/pi_lan_2clients_r5_s42"'
```
Benchmarks: PC `python scripts/35_performance_benchmark.py --device-label pc_i7-13620H_wsl2`; Pi (clone of commit 004444e at ~/seniorfl/repo_v1) `python scripts/35_performance_benchmark.py --device-label pi5_model_b_8gb_arm64`.
