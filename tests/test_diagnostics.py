import unittest
from pathlib import Path

from sourcebox.diagnostics import diagnostic_log_path


class DiagnosticPathTests(unittest.TestCase):
    def test_macos_log_uses_library_logs(self):
        path = diagnostic_log_path(system="Darwin", environment={}, home="/Users/test")
        self.assertEqual(
            path,
            Path("/Users/test/Library/Logs/SourceBox/sourcebox.log"),
        )

    def test_windows_log_prefers_local_app_data(self):
        path = diagnostic_log_path(
            system="Windows",
            environment={"LOCALAPPDATA": "C:/Users/test/AppData/Local"},
            home="C:/Users/test",
        )
        self.assertEqual(
            path,
            Path("C:/Users/test/AppData/Local/SourceBox/sourcebox.log"),
        )
