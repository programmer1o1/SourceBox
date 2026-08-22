"""
Mapbase bridge helper for SourceBox.
Provides basic path preparation for mapbase-based sourcemods so VScript
features can be dropped in automatically.
"""

import os

from sourcebox.resources import load_text_resource


class MapbaseBridge:
    def __init__(self, mod_path, verbose=False):
        self.mod_path = os.path.abspath(mod_path)
        self.verbose = verbose
        self.scriptdata_path = os.path.join(self.mod_path, "vscript_io")
        self.vscripts_path = os.path.join(self.mod_path, "scripts", "vscripts")
        self.command_file = os.path.join(self.scriptdata_path, "python_command.txt")
        self.response_file = os.path.join(self.scriptdata_path, "python_response.txt")

    def prepare_paths(self):
        """create required folders for VScript bridge files"""
        try:
            os.makedirs(self.scriptdata_path, exist_ok=True)
            os.makedirs(self.vscripts_path, exist_ok=True)
            return True
        except Exception as e:
            if self.verbose:
                print(f"[error] mapbase path setup failed: {e}")
            return False

    def install_scripts(self):
        """Install complete, ready-to-use VScript files"""
        scripts = {
            "auto_spawner.nut": self._get_auto_spawner_script(),
            "picker.nut": self._get_picker_script(),
            "python_listener.nut": self._get_python_listener_script(),
            "vscript_server.nut": self._get_vscript_server_script()
        }

        for filename, content in scripts.items():
            dest = os.path.join(self.vscripts_path, filename)
            try:
                with open(dest, "w", encoding="utf-8", newline="\n") as f:
                    f.write(content)
                if self.verbose:
                    print(f"[installed] {filename}")
            except Exception as e:
                if self.verbose:
                    print(f"[warning] failed to write {dest}: {e}")

    def _get_auto_spawner_script(self):
        """return complete auto_spawner.nut script"""
        return load_text_resource("bridge_scripts/mapbase/auto_spawner.nut")

    def _get_picker_script(self):
        """return complete picker.nut script"""
        return load_text_resource("bridge_scripts/mapbase/picker.nut")

    def _get_python_listener_script(self):
        """return complete python_listener.nut script"""
        return load_text_resource("bridge_scripts/mapbase/python_listener.nut")

    def _get_vscript_server_script(self):
        """return complete vscript_server.nut script"""
        return load_text_resource("bridge_scripts/mapbase/vscript_server.nut")

    @staticmethod
    def looks_mapbase(path):
        """quick check if a path is the mapbase folder or sits beside it"""
        if not path:
            return False

        abs_path = os.path.abspath(path)
        base_name = os.path.basename(abs_path).lower()
        if base_name == "mapbase":
            return True

        parent_dir = os.path.dirname(abs_path)
        return os.path.isdir(os.path.join(parent_dir, "mapbase"))
