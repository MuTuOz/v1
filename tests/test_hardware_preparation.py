from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'hardware_deployment/app'))
from pifl.common import SCHEMA,class_weights,validate_checkpoint_metadata
from pifl.client_app import data_path,fingerprint
from flwr.common import Context,RecordDict


class HardwarePreparationTests(unittest.TestCase):
    def test_checkpoint_schema_includes_class_order(self):
        d={k:SCHEMA[k] for k in ['features','classes','family_of','preprocessing']};validate_checkpoint_metadata(d)
        changed={**d,'classes':list(reversed(d['classes']))}
        with self.assertRaises(ValueError):validate_checkpoint_metadata(changed)
    def test_partial_new_training_support_unweighted(self):
        self.assertIsNone(class_weights([0]*84,'unweighted'))
        with self.assertRaises(ValueError):class_weights([0]*84,'inverse_frequency')
    def test_node_local_path_and_holdout_guard(self):
        def context(path):return Context(run_id=1,node_id=2,node_config={'client-id':2,'data-path':path},state=RecordDict(),run_config={})
        self.assertEqual(data_path(context('/tmp/client2_train.csv'),{}),Path('/tmp/client2_train.csv'))
        with self.assertRaises(ValueError):data_path(context('/tmp/validation.csv'),{})
    def test_schema_fingerprint_deterministic(self):self.assertEqual(len(fingerprint()),64);self.assertEqual(fingerprint(),fingerprint())


if __name__=='__main__':unittest.main()
