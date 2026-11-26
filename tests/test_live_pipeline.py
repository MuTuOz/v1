from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from live_pipeline.extract import aggregate_packets,feature_contract,model_ready
from scapy.all import Ether,IP,TCP,UDP,Raw


class OfflineFeatureTests(unittest.TestCase):
    def packets(self):
        a=Ether(src='02:00:00:00:00:01',dst='02:00:00:00:00:02')/IP(src='192.0.2.1',dst='192.0.2.2',ttl=64)/TCP(sport=1000,dport=80,flags='S')/Raw(b'abc');a.time=0.
        b=Ether(src='02:00:00:00:00:02',dst='02:00:00:00:00:01')/IP(src='192.0.2.2',dst='192.0.2.1',ttl=60)/TCP(sport=80,dport=1000,flags='A');b.time=4.99
        c=Ether(src='02:00:00:00:00:01',dst='02:00:00:00:00:02')/IP(src='192.0.2.1',dst='192.0.2.2')/UDP(sport=10,dport=20);c.time=5.
        return [a,b,c]
    def test_half_open_windows_and_direction(self):
        rows=aggregate_packets(self.packets(),'192.0.2.1')
        self.assertEqual([r['window_start_utc_seconds'] for r in rows],[0.,5.])
        f=rows[0]['features'];self.assertEqual(f['network_packets_all_count'],2)
        self.assertEqual(f['network_packets_src_count'],1);self.assertEqual(f['network_packets_dst_count'],1)
        self.assertEqual(f['network_tcp-flags-ack_count'],1);self.assertEqual(f['network_ttl_avg'],62.)
    def test_missing_logs_never_zero_filled(self):
        row=aggregate_packets(self.packets(),'192.0.2.1')[0]
        self.assertIsNone(row['features']['log_messages_count'])
        with self.assertRaises(ValueError):model_ready(row)
    def test_explicit_log_alignment(self):
        logs=[{'timestamp':1.,'monitor_id':'192.0.2.1','data_type':'temperature'},
              {'timestamp':2.,'monitor_id':'192.0.2.1','data_type':'pressure'}]
        f=aggregate_packets(self.packets(),'192.0.2.1',logs)[0]['features']
        self.assertEqual(f['log_messages_count'],2);self.assertEqual(f['log_data-types_count'],2)
        self.assertIsNone(f['log_data-ranges_avg'])
    def test_unrelated_traffic_excluded(self):self.assertEqual(aggregate_packets(self.packets(),'192.0.2.99'),[])
    def test_schema_complete(self):
        c=feature_contract();self.assertEqual(len(c),71)
        self.assertTrue(all(f['dataset_semantic_parity']=='not verified' for f in c))
    def test_no_neighbor_resolution_or_packet_send(self):
        with patch('scapy.layers.l2.getmacbyip',side_effect=AssertionError('Neighbor resolution forbidden')):
            with patch('scapy.sendrecv.send',side_effect=AssertionError('Sending forbidden')):
                packets=self.packets()
                for packet in packets:bytes(packet)
                rows=aggregate_packets(packets,'192.0.2.1')
                self.assertEqual(len(rows),2)
    def test_unspecified_mac_is_rejected(self):
        packet=Ether()/IP(src='192.0.2.1',dst='192.0.2.2')/TCP()
        packet.time=0
        with patch('scapy.layers.l2.getmacbyip',side_effect=AssertionError('No ARP')):
            with self.assertRaises(ValueError):aggregate_packets([packet],'192.0.2.1')


if __name__=='__main__':unittest.main()
