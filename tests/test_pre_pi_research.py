import json
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd
import torch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'pre_pi_app'))
from researchfl.common import CLASSES, FEATURES, MLP, class_weights, prepare, train_path
from researchfl.evaluation import masks_for_support, score


class ResearchProtocolTests(unittest.TestCase):
    def test_training_only_paths(self):
        for i in range(1,6):
            self.assertEqual(train_path(ROOT,{'partition':'original'},i).name,f'client_{i}_train.csv')
        with self.assertRaises(ValueError):train_path(ROOT,{'partition':'invented'},1)
    def test_weights_training_counts(self):
        counts=[1]+[10]*83
        for method in ['inverse_frequency','effective_number']:
            w=class_weights(counts,method)
            self.assertGreater(w[0],w[1]);self.assertAlmostEqual(float(w.mean()),1.,places=5)
            self.assertTrue(torch.isfinite(w).all())
        with self.assertRaises(ValueError):class_weights([0]*84,'inverse_frequency')
    def test_compatible_preprocessing(self):
        sys.path.insert(0,str(ROOT/'flower_subtype_app'))
        from seniorfl_subtype.task import prepare as old
        d=pd.DataFrame([[float('nan'),float('inf'),-1e20]+[1.]*68],columns=FEATURES)
        torch.testing.assert_close(prepare(d),old(d),rtol=0,atol=0)
        self.assertEqual(sum(t.numel() for t in MLP().parameters()),9460)
    def test_unseen_split(self):
        train={'benign','ddos_http-flood-port-80'}
        val=['benign','ddos_http-flood-port-80','ddos_tcp-flood-port-80','dos_tcp-flood-port-80']
        m=masks_for_support(train,val)
        np.testing.assert_array_equal(m['A_unseen_subtype'],[False,False,True,True])
        np.testing.assert_array_equal(m['B_unseen_family'],[False,False,False,True])
        np.testing.assert_array_equal(m['C_unseen_subtype_known_family'],[False,False,True,False])
    def test_balanced_all_seen_and_empty_subset(self):
        m=masks_for_support(set(CLASSES),['benign',CLASSES[1]])
        self.assertFalse(any(mask.any() for mask in m.values()))
        empty=score([],[],ROOT)
        self.assertEqual(empty['status'],'unsupported_empty_subset');self.assertIsNone(empty['hcm_f1'])
    def test_hcm_reuses_verified_implementation(self):
        from hcm_eval import project_hierarchy
        schema=json.loads((ROOT/'flower_subtype_app/seniorfl_subtype/schema.json').read_text())
        tree,leaves=project_hierarchy(schema)
        for t,p in [(0,0),(1,2),(1,0),(0,1),(1,30)]:
            m=score([t],[p],ROOT)
            self.assertEqual(m['hcm_counts'],tree.contribution(leaves[CLASSES[t]],leaves[CLASSES[p]]).to_dict())
            self.assertEqual(sum(m['hierarchical_errors'].values()),1)
    def test_unseen_metrics_denominators(self):
        m=score([1,2],[0,2],ROOT)
        self.assertEqual(m['attack_detection_recall'],.5)
        self.assertIsNone(m['benign_false_positive_rate'])
        with self.assertRaises(ValueError):score([84],[0],ROOT)


if __name__=='__main__':unittest.main()
