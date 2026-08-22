import hashlib
from pathlib import Path
import unittest

from mapbase_bridge import MapbaseBridge


ROOT = Path(__file__).resolve().parent.parent

EXPECTED_SHA256 = {
    "bridge_scripts/mapbase/auto_spawner.nut": "ef1221de2074081a307d1dafa8ec296b7fa29ea9912d2cbe65a549abb5a2ceb8",
    "bridge_scripts/mapbase/picker.nut": "8ea50f7839b412f8393bb64eabedb7730afe7acf830b81b33b2c60a9e9a552d2",
    "bridge_scripts/mapbase/python_listener.nut": "a69913c85123dbfa7f0ccbc0640e8ab9f2237611908312a1a6eb6a11f60b9509",
    "bridge_scripts/mapbase/vscript_server.nut": "1fd76513a8365a5cef281e20452fc5afeb03f98266911b48dc12a6db0e3bd2d8",
    "bridge_scripts/gmod/gmod9/sv_picker.lua": "8607014768830d7b930ef4c5e090d5d153a5db878ec6e83a2dc95db031bb2006",
    "bridge_scripts/gmod/gmod9/sv_auto_spawner.lua": "a45b6bad7c1fed4ad8ffd98bd0a64e612b722a085aac048d8d14e4c01e33a68d",
    "bridge_scripts/gmod/gmod9/sv_python_listener.lua": "f7fcac358a5d60cd79ffbd97190c335f0908935f0187addaed44146e5b3d8971",
    "bridge_scripts/gmod/modern/sourcebox_init.lua": "bb62429f6b6d1c935d6ecc6c192dd699a88d2a4d19093b2466fd1527d786731d",
    "bridge_scripts/gmod/modern/sv_python_bridge.lua": "ea0dddb0356a7ca796c6f364b840d7e10b4c30a6500060fd650b9bd1c870cf03",
    "bridge_scripts/gmod/modern/sv_picker.lua": "9146c471937a73ca510992d89e1b072dec1f9145cb847312f71cb21a94940760",
    "bridge_scripts/gmod/modern/sv_auto_spawner.lua": "cbc3d0c6f295818be86e2bcc2d9aff427f509c709441d5bdba7c3dd5835f1aac",
    "bridge_scripts/source/picker.nut": "64dfa78016aa042990df634b836bc96f9df1d8a35488aa608d24ea48c2c8e983",
    "bridge_scripts/source/awp_quit.nut": "aaea32589dc67314427a6d2c03be1ccff891db9cb45fa2d1f424e9c191841211",
    "bridge_scripts/source/auto_spawner.nut": "416f43885c04e5dfccdefeaad09861545a0daf42526f40b867c0f5a9e0846ed7",
    "bridge_scripts/source/python_listener.nut": "847c648a56f95bd8978f0472f1942d5926150d1abbb8493407d1d109688a990b",
}


class BridgeScriptSnapshotTests(unittest.TestCase):
    def test_extracted_scripts_are_byte_for_byte_equivalent(self):
        for relative_path, expected in EXPECTED_SHA256.items():
            with self.subTest(script=relative_path):
                content = (ROOT / relative_path).read_bytes()
                self.assertEqual(hashlib.sha256(content).hexdigest(), expected)

    def test_mapbase_bridge_loads_extracted_resources(self):
        bridge = MapbaseBridge("/tmp/sourcebox-mapbase-test")
        method_paths = {
            bridge._get_auto_spawner_script: "bridge_scripts/mapbase/auto_spawner.nut",
            bridge._get_picker_script: "bridge_scripts/mapbase/picker.nut",
            bridge._get_python_listener_script: "bridge_scripts/mapbase/python_listener.nut",
            bridge._get_vscript_server_script: "bridge_scripts/mapbase/vscript_server.nut",
        }
        for method, relative_path in method_paths.items():
            with self.subTest(script=relative_path):
                self.assertEqual(method(), (ROOT / relative_path).read_text())


if __name__ == "__main__":
    unittest.main()
