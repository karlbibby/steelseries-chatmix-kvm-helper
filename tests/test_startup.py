import unittest
from unittest.mock import patch
import gg_chatmix_helper as helper

class Startup(unittest.TestCase):
    def test_shell_launch_failure_does_not_crash_startup_watcher(self):
        error = OSError('Elevation required')
        error.winerror = 740
        with patch.object(helper, 'gg_processes', return_value=()), \
             patch.object(helper.os, 'startfile', side_effect=error):
            self.assertFalse(helper.launch_gg(startup=True))

    def test_does_not_launch_duplicate_host_when_gg_running(self):
        with patch.object(helper, 'gg_processes', return_value=(('steelseriesgg.exe',123),)), \
             patch.object(helper.os, 'startfile') as spawn:
            self.assertTrue(helper.launch_gg(startup=True))
            spawn.assert_not_called()

    def test_other_startup_errors_are_not_silenced(self):
        with patch.object(helper, 'gg_processes', return_value=()), \
             patch.object(helper.os, 'startfile', side_effect=FileNotFoundError('Missing GG')):
            with self.assertRaises(FileNotFoundError):
                helper.launch_gg(startup=True)

    def test_cold_start_uses_shell_launch_with_background_arguments(self):
        with patch.object(helper, 'gg_processes', return_value=()), \
             patch.object(helper.os, 'startfile') as shell, \
             patch.object(helper.subprocess, 'Popen') as direct:
            self.assertTrue(helper.launch_gg(startup=True))
        direct.assert_not_called()
        args = shell.call_args.args
        self.assertEqual(args[0], str(helper.GG_HOST))
        self.assertEqual(args[1], 'open')
        self.assertIn('-auto=true', args[2])
        self.assertEqual(args[3], str(helper.GG.parent))
        self.assertEqual(args[4], 0)

if __name__ == '__main__':
    unittest.main()
