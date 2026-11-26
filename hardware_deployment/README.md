# Prepared physical-client package

This is a separate Flower 1.40.0 deployment app. It supports two clients first,
then 3–5 by configuration. It is not the fixed-five-partition simulation app.
No Pi hardware execution is claimed. See `docs/pi_deployment_readiness.md` and
the recorded local-process smoke evidence before describing readiness.

1. Use a 64-bit OS and a supported Python 3.12 environment on every node.
   Review ARM64 torch/Flower availability first; the x86 dependency freeze is
   not an ARM lockfile. `scripts/setup_env.sh` only runs when explicitly invoked,
   creates a new user-owned environment and never uses sudo.
2. Provision separate CA-signed endpoint certificates and per-node identity
   keys outside the repository. TLS server names must match SANs. Follow the
   pinned runtime's node-registration/authentication guide. Do not log keys.
3. Copy `app/` to server/clients or build a versioned FAB, with schema and source
   hashes. Run the local-only `scripts/healthcheck.py` against each client-local
   training CSV and the intended initial checkpoint. Labels/features must
   match the frozen schema. Live extraction parity is a separate prerequisite.
4. Prepare a new server experiment configuration based on the smoke config:
   actual `num_clients` (2–5), `clients_per_round`, seed, final-round budget,
   hyperparameters, loss/class counts, features, root and experiment ID. Configure
   a fresh output directory. Use a separate run-config TOML pointing to it.
   Optional `initial_checkpoint` resumes from a declared checkpoint, with new
   round-local Adam state. Record cumulative/new-only/replay data policy.
5. The laptop runs `flower-superlink` with TLS certificates, approved node
   authentication and local Runtime API scope. Each Pi runs `flower-supernode`
   with the trusted CA, its own identity key, a stable `client-id`, its local
   `data-path`, and a `log-dir` in `--node-config`. Never use laptop absolute
   paths as a substitute for each Pi's local training file.
6. Submit `flwr run hardware_deployment/app <tls-profile> --run-config <new.toml>
   --stream` only after isolation and identity checks. Review the completed
   model and all required replies; CLI success alone is insufficient.

The client validates the schema fingerprint, trains only its configured local
CSV, measures training wall time/RSS and serialized array sizes, and logs ten
warm inference-batch timings per round. These batch timings are not independent
single-record latency measurements. Server aggregation checks all configured
selected client IDs, sizes and actual sample-weighted tensors. Measured record
payloads exclude wire, TLS, configuration and retransmission overhead.

Health checks do not capture/send packets. The separate smoke runner deliberately
uses loopback and synthetic local CSVs only, starts two independent Linux
SuperNode processes, and shuts down only those processes. It never configures
interfaces/firewalls or generates laboratory attacks. Physical TLS trust,
ARM compatibility, node identity provisioning, capture feature parity and
device performance still require verification on the actual lab devices.
