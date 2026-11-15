import unittest
from unittest.mock import Mock, patch
import probe_headset as probe

def target(suffix='one'):
    return {'path': rf'\\?\hid#vid_1038&pid_12e0&mi_04&col01#{suffix}',
            'caps': {'UsagePage': 0xFFC0, 'InputReportByteLength': 64, 'OutputReportByteLength': 64}}

class CommandSafety(unittest.TestCase):
    def test_multiple_devices_rejected_before_open_or_send(self):
        kernel, setup, hid = Mock(), Mock(), Mock()
        with patch.object(probe, 'inventory', return_value=[target('one'), target('two')]):
            with self.assertRaisesRegex(RuntimeError, 'Multiple'):
                probe.run((kernel, setup, hid), enable=True)
        kernel.CreateFileW.assert_not_called()
        hid.HidD_SetOutputReport.assert_not_called()

    def test_inventory_mode_does_not_open_command_handle(self):
        kernel, setup, hid = Mock(), Mock(), Mock()
        with patch.object(probe, 'inventory', return_value=[target()]):
            probe.run((kernel, setup, hid))
        kernel.CreateFileW.assert_not_called()
        hid.HidD_SetOutputReport.assert_not_called()

    def test_enable_only_sends_two_commands_without_reading_events(self):
        kernel, setup, hid = Mock(), Mock(), Mock()
        kernel.CreateFileW.return_value = 123
        with patch.object(probe, 'inventory', return_value=[target()]), \
             patch.object(probe, 'control_report', return_value={'ok': True}) as send, \
             patch.object(probe, 'overlapped_io') as read:
            probe.run((kernel, setup, hid), enable=True)
        self.assertEqual([call.args[2] for call in send.call_args_list], [b'\x06\x49\x01',b'\x06\x8d\x01'])
        read.assert_not_called()
        kernel.CloseHandle.assert_called_once_with(123)

    def test_persistent_or_unknown_commands_rejected(self):
        hid = Mock()
        for command in (b'\x06\x09', b'\x06\xbd\x02', b'\x00'):
            with self.assertRaises(ValueError):
                probe.control_report(hid, 123, command)
        hid.HidD_SetOutputReport.assert_not_called()

    def test_wrong_collection_or_report_size_not_selected(self):
        wrong = target()
        wrong['caps']['OutputReportByteLength'] = 1024
        self.assertIsNone(probe.select_target([wrong]))

if __name__ == '__main__':
    unittest.main()
