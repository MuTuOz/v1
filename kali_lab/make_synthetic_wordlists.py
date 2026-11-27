#!/usr/bin/env python3
"""Generate a small SYNTHETIC user/password list for bruteforce_* scenarios.

Deliberately does not use a real leaked-password dump (rockyou.txt etc.) or
any real account credentials. The target must have a disposable test account
created with one of these passwords on purpose, so the dictionary hits.

Usage:
    python3 make_synthetic_wordlists.py --out-dir wordlists --hit-password lab-test-pw-7f3a
"""
import argparse
import random
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="wordlists", type=Path)
    ap.add_argument("--users", nargs="+", default=["labtest", "iotuser", "pi"])
    ap.add_argument("--hit-password", required=True,
                    help="the password you actually set on the target's disposable test account")
    ap.add_argument("--decoy-count", type=int, default=49)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    a.out_dir.mkdir(parents=True, exist_ok=True)
    (a.out_dir / "users.txt").write_text("\n".join(a.users) + "\n")

    rng = random.Random(a.seed)
    decoys = [f"decoy-{rng.getrandbits(32):08x}" for _ in range(a.decoy_count)]
    passwords = decoys[: a.decoy_count // 2] + [a.hit_password] + decoys[a.decoy_count // 2 :]
    (a.out_dir / "passwords.txt").write_text("\n".join(passwords) + "\n")
    print(f"wrote {a.out_dir / 'users.txt'} ({len(a.users)} users) and "
         f"{a.out_dir / 'passwords.txt'} ({len(passwords)} passwords, hit at position "
         f"{passwords.index(a.hit_password) + 1})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
