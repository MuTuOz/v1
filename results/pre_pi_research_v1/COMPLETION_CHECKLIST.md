# Completion checklist

| Phase | Status | Executed evidence / remaining boundary |
|---|---|---|
| 1 Local-only baselines | COMPLETE | Five independent seed-42 checkpoints, fixed-validation reports and model inference verification. |
| 2 Client-relative unseen | COMPLETE | Identical A/B/C masks, three-way per-client/per-class comparison and explicit empty subsets. |
| 3 Repeated seeds | COMPLETE | Three predefined seeds × centralized/Flower/five locals, mean/SD and per-seed artifacts. |
| 4 Imbalance controls | COMPLETE | Unweighted reference + inverse-frequency/effective-number training-derived controls; seed-42 global and local arms. |
| 5 Non-IID/participation | COMPLETE | Two new audited training-only allocations, full/3-of-5 participation and E=1/E=2 controls; true Flower runs. |
| 6 Hierarchical evaluation | COMPLETE | Existing verified formal HCM applied to every model/subset; flat/family/detection matrices and figures preserved. |
| 7 Streamlit dashboard | COMPLETE | Artifact-driven 11-view app; AppTest and actual loopback HTTP health passed. Browser screenshots not captured. |
| 8 Pi deployment preparation | PARTIAL | Reusable app/templates/setup/health scripts and two independent Linux SuperNodes over TLS tested. ARM64/Pi execution and registered-node auth remain unverified. |
| 9 Live feature pipeline | PARTIAL | 71-slot nullable contract, 53 candidate definitions, guarded offline PCAP prototype/tests and drift diagnostics. Exact source semantics/18 slots/log parity blocked by missing authoritative extractor/docs. |
| 10 Isolated Kali preparation | COMPLETE (DESIGN ONLY) | Roles/topology/IP/inventory/labels/session protocol documented. No live attacks or interface changes requested or performed. |
| 11 Academic deliverables | COMPLETE (DRAFTS) | Methods, measured Results, Threats, figures/tables, demo and presentation outline; no publication-readiness claim. |

COMPLETE refers to the requested software/experiment/design scope and requires the final verification file. It does not mean physical hardware, independent-session evaluation or full 84-class coverage is complete.
