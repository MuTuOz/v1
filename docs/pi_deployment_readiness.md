# Raspberry Pi deployment readiness — pre_pi_research_v1

**Software preparation is tested on x86 Linux; physical Raspberry Pi execution is
not verified.** No purchase, device connection, network configuration or attack
execution was performed. The deployment package is `hardware_deployment/`.

## Verified offline/software evidence

| Capability | Actual evidence |
|---|---|
| Reusable ClientApp / ServerApp | Separate `hardware_deployment/app/pifl/`; node-local CSVs, stable client IDs, configurable 2–5 clients |
| Checkpoint/schema guard | Classes/order, 71 features/order, family mapping, preprocessing and client/server schema fingerprint checked |
| Training/aggregation | Two independent Linux SuperNode processes, 2 rounds, 4 successful updates on 16 synthetic training rows per client |
| TLS | Loopback SuperLink and node Runtime APIs use an ephemeral test CA; untrusted-CA connection rejected |
| Per-device measurements | Four JSON logs include training wall time, RSS, ten warmed inference-batch timings and serialized ArrayRecord sizes |
| Environment/setup | User-owned venv setup script, dependency requirements, local-only health check and config templates |

Evidence: [TLS smoke verification](../results/pre_pi_research_v1/phase08/loopback_tls_smoke/verification.json),
[x86 checkpoint/data health check](../results/pre_pi_research_v1/phase08/healthcheck_x86.json),
the smoke `device_1/` / `device_2/` logs and round histories. The smoke is not
an IDS accuracy experiment; its random feature CSVs are explicitly synthetic.
Test private keys remain outside project artifacts in a restricted temporary
directory; only certificate fingerprints and paths are recorded. Test credentials
are not production credentials.

The final package also passed a separate [checkpoint continuation smoke](../results/pre_pi_research_v1/phase08/loopback_tls_checkpoint_v4/verification.json):
two independent SuperNodes, two rounds/four updates starting from the preserved
Flower checkpoint, schema validation and untrusted-CA rejection. Python/schema
files in the installed FAB match the current source bytes; Flower's reserialized
`pyproject.toml` matches semantically. Two earlier continuation attempts completed
their updates but failed final bookkeeping checks; their models/logs are retained
and are not marked verified. No scientific accuracy result is derived from these
synthetic smoke runs. The [final local health check](../results/pre_pi_research_v1/phase08/healthcheck_final_schema_guard_x86.json)
also verifies the complete checkpoint metadata guard.

## Steps after devices arrive

1. Record Pi model, RAM, 64-bit OS, Python version, storage and power supply.
   Verify ARM64 wheels for Flower 1.40.0, torch and dependencies before changing
   project versions. The x86 freeze is evidence, not a portable ARM lockfile.
2. Provision separate management/experiment networks using the approved lab
   plan. Verify WSL2 reachability with scoped lab endpoints; do not expose
   vulnerable services or Flower management to the Internet.
3. Issue unique node identity credentials and CA-signed endpoint certificates.
   Check SANs/expiry and register intended nodes with the selected runtime's
   CLI-managed authentication. **Registered-node authentication was not exercised
   in the current smoke**, which tested TLS trust and application client identity.
   Server-authenticated TLS is not mTLS or secure aggregation.
4. Copy/install the versioned hardware app and checkpoint. Run
   `hardware_deployment/scripts/healthcheck.py` locally on each device. Require
   parity on the same serialized golden inputs; a tensor shape check alone does
   not verify live feature semantics.
5. Create fresh labelled client-local training versions and independent session
   evaluation records. Bind client IDs to device inventory and local data/log
   paths. Begin with two clients; expand `num_clients` and participation to 3–5
   only after identity, sample-count and failure handling are verified.
6. Configure a new server experiment JSON/run-config and a fresh output path.
   Pin initial checkpoint lineage, seed, optimizer reset policy, sample counts
   and budgets. Submit the app only after the manual rollout gate is met.
7. Measure real inference/training latency, RSS, round time and communication
   separately from x86 smoke numbers. ArrayRecord sizes are application payloads,
   not wire/TLS/transport totals. Energy needs an actual instrument, not inference
   from wall time.

The original simulation app has five fixed logical client partitions. Hardware
SuperNodes are independent long-running processes with node-local storage;
the laptop is the coordinator, not a data path shared across devices. The
prepared app supplies configuration via messages and reads each node's own CSV.
Its `initial_checkpoint` option enables a declared continuation run once new
training labels exist. Unweighted training supports partially observed class
sets; weighted methods require a defined positive global training-support
policy and must not derive weights from evaluation records.

No dashboard button launches training, captures traffic or changes the network.
See [feature compatibility](live_feature_compatibility_report.md) and
[isolated Kali protocol](kali_lab_deployment_plan.md) for remaining acceptance
criteria. Exact live feature parity, ARM execution, registered-node auth and
independent physical-session evaluation remain CS402 work.
