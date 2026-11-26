"""Regression: a manifest must exclude itself, not the last artifact iterated."""
import hashlib
import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class VerifierTests(unittest.TestCase):
    def test_manifest_self_exclusion_and_latest_revision(self):
        module = runpy.run_path(str(ROOT / "scripts/33_verify_pre_pi.py"))
        env = module["verify_manifest"].__globals__
        with tempfile.TemporaryDirectory(prefix="seniorproject-verifier-") as temporary:
            root = Path(temporary)
            out = root / "results"
            out.mkdir()
            files = {}
            for name in ["a.txt", "z.txt"]:
                data = name.encode()
                path = out / name
                path.write_bytes(data)
                files[str(path.relative_to(root))] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            manifest = out / "ARTIFACT_MANIFEST_revision_03.json"
            manifest.write_text(json.dumps({"files": files}))
            with patch.dict(env, {"ROOT": root, "OUT": out, "source_files": lambda: []}):
                self.assertEqual(module["latest_manifest"](), manifest)
                self.assertEqual(module["verify_manifest"](manifest), 2)
                self.assertEqual(module["verify_manifest"](), 2)


if __name__ == "__main__":
    unittest.main()
