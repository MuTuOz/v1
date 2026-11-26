from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest

ROOT=Path(__file__).resolve().parents[1]


class DashboardTests(unittest.TestCase):
    def test_all_views_and_model_selection(self):
        app=AppTest.from_file(str(ROOT/'dashboard/app.py'),default_timeout=40).run()
        self.assertFalse(app.exception)
        for page in app.sidebar.selectbox(key='page').options:
            app.sidebar.selectbox(key='page').set_value(page).run()
            self.assertFalse(app.exception,page)
        app.sidebar.selectbox(key='experiment').set_value('ref_local_c1_s42').run()
        app.sidebar.selectbox(key='page').set_value('Confusion matrices').run()
        for level in ['detection','family','subtype']:
            app.sidebar.selectbox(key='level').set_value(level).run();self.assertFalse(app.exception)

    def test_unseen_comparison_matches_support_and_handles_empty(self):
        app=AppTest.from_file(str(ROOT/'dashboard/app.py'),default_timeout=40).run()
        app.sidebar.selectbox(key='page').set_value('Locally unseen attacks').run()
        self.assertFalse(app.exception)
        data=app.dataframe[0].value
        self.assertEqual(len(data),3)
        self.assertEqual(data.samples.unique().tolist(),[2192])
        self.assertEqual(set(data['mode']),{'local_only','flower_fedavg','centralized'})
        app.checkbox(key='unseen_controls').set_value(True).run()
        app.selectbox(key='unseen_allocation').set_value('balanced').run()
        self.assertFalse(app.exception)
        self.assertEqual(app.dataframe[0].value.samples.unique().tolist(),[0])
        self.assertTrue(any('Unsupported / empty subset' in box.value for box in app.info))


if __name__=='__main__':unittest.main()
