import os
import json
import shutil
import time
import zipfile
import sys

class StorageManager:
    def __init__(self, data_dir=None):
        if data_dir:
            self.data_dir = data_dir
        else:
            self.data_dir = os.path.join(os.getcwd(), "data")
            
        self.library_dir = os.path.join(self.data_dir, "library")
        self.packs_dir = os.path.join(self.data_dir, "packs")
        self.modpacks_file = os.path.join(self.data_dir, "modpacks.json")
        self.config_file = os.path.join(self.data_dir, "config.json")
        self.temp_backups_dir = os.path.join(self.data_dir, "temp_backups")
        self.library_file = os.path.join(self.data_dir, "library.json")

        self.ensure_directories()
        self.init_files()
        self.config = self.load_config()

        # Migration logic
        self.migrate_library_ids()

    def ensure_directories(self):
        for d in [self.data_dir, self.library_dir, self.packs_dir, self.temp_backups_dir]:
            if not os.path.exists(d):
                os.makedirs(d)

    def init_files(self):
        if not os.path.exists(self.modpacks_file):
            with open(self.modpacks_file, 'w') as f:
                json.dump([], f)
                
        if not os.path.exists(self.library_file):
            with open(self.library_file, 'w') as f:
                json.dump({}, f)

    def load_config(self):
        default = {
            "api_key": "",
            "game_dir": "",
            "manage_saves": False,
            "active_modpack": None,
            "use_symlinks": True
        }
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    default.update(data)
            except: pass
        return default

    def save_config(self, new_config):
        self.config.update(new_config)
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f)
        return {"status": "success"}

    def load_library(self):
        try:
            with open(self.library_file, 'r') as f:
                return json.load(f)
        except:
            return {}

    def save_library(self, lib_data):
        with open(self.library_file, 'w') as f:
            json.dump(lib_data, f)

    def load_modpacks(self):
        with open(self.modpacks_file, 'r') as f:
            return json.load(f)
            
    def save_modpacks_data(self, packs):
        with open(self.modpacks_file, 'w') as f:
            json.dump(packs, f)

    def _extract_internal_id(self, file_path):
        """Extracts Namespace:Name from manifest.json inside mod zip/jar"""
        try:
            if not os.path.exists(file_path): return None
            
            with zipfile.ZipFile(file_path, 'r') as z:
                if 'manifest.json' in z.namelist():
                    with z.open('manifest.json') as f:
                        data = json.load(f)
                        group = data.get("Group", "Unknown")
                        name = data.get("Name", "Unknown")
                        return f"{group}:{name}"
        except Exception as e:
            print(f"Error extracting ID from {file_path}: {e}")
        return None

    def migrate_library_ids(self):
        """Adds internal_id to all mods in library.json if missing"""
        lib = self.load_library()
        changed = False
        for mid, info in lib.items():
            if "internal_id" not in info or info["internal_id"] == "Unknown:Unknown":
                file_path = os.path.join(self.library_dir, info.get("file_name", ""))
                internal_id = self._extract_internal_id(file_path)
                if internal_id:
                    info["internal_id"] = internal_id
                    changed = True
                else:
                    info["internal_id"] = "Unknown:Unknown"
                    changed = True
        
        if changed:
            self.save_library(lib)
            print("[Migration] Library internal IDs updated.")

    def try_auto_detect_game(self):
        """Attempts to find Hytale based on default paths"""
        if sys.platform.startswith('linux'):
            # Path: ~/.var/app/com.hypixel.HytaleLauncher/data/Hytale
            path = os.path.expanduser("~/.var/app/com.hypixel.HytaleLauncher/data/Hytale")
            if os.path.exists(path): return path
        elif sys.platform == 'win32':
            # Path: %APPDATA%/Hytale
            appdata = os.getenv('APPDATA')
            if appdata:
                path = os.path.join(appdata, "Hytale")
                if os.path.exists(path): return path
        return ""

    def clear_directory(self, path):
        """Removes all contents of a directory without removing the directory itself"""
        if not os.path.exists(path): return
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            try:
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                else:
                    os.remove(item_path)
            except Exception as e:
                print(f"Failed to delete {item_path}: {e}")

    def get_screenshots(self):
        home = os.path.expanduser('~')
        candidates = [
            os.path.join(home, 'Pictures', 'Hytale Screenshots'),
            os.path.join(home, 'Imagens', 'Hytale Screenshots'),
            os.path.join(home, 'Pictures'),
            os.path.join(home, 'Imagens')
        ]
        target_dir = next((p for p in candidates if os.path.exists(p)), None)
        
        if not target_dir: return []
        
        files = [f for f in os.listdir(target_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        # Sort by modification time (newest first)
        files.sort(key=lambda x: os.path.getmtime(os.path.join(target_dir, x)), reverse=True)
        return files

    def get_pack_logs(self, pack_name):
        saves_dir = os.path.join(self.packs_dir, pack_name, "saves")
        if not os.path.exists(saves_dir): return []
        
        all_logs = []
        try:
            for save in os.listdir(saves_dir):
                log_dir = os.path.join(saves_dir, save, "logs")
                if os.path.exists(log_dir) and os.path.isdir(log_dir):
                    for log_file in os.listdir(log_dir):
                        if log_file.endswith(".log"):
                            path = os.path.join(log_dir, log_file)
                            all_logs.append({
                                "file": log_file,
                                "save": save,
                                "time": os.path.getmtime(path)
                            })
        except: pass
        
        all_logs.sort(key=lambda x: x['time'], reverse=True)
        return all_logs

    def read_log_file(self, pack_name, save_name, file_name):
        path = os.path.join(self.packs_dir, pack_name, "saves", save_name, "logs", file_name)
        if not os.path.exists(path): return "Arquivo não encontrado."
        
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception as e:
            return f"Erro ao ler log: {e}"

    def delete_mod_from_library(self, mod_id):
        lib = self.load_library()
        sid = str(mod_id)
        if sid in lib:
            fname = lib[sid].get("file_name")
            if fname:
                p = os.path.join(self.library_dir, fname)
                if os.path.exists(p):
                    try: os.remove(p)
                    except: pass
            del lib[sid]
            self.save_library(lib)
            return True
        return False

    def get_modpack(self, name):
        packs = self.load_modpacks()
        return next((p for p in packs if p['name'] == name), None)

    def save_modpack(self, pack_data):
        packs = self.load_modpacks()
        # Remove existing if updates
        packs = [p for p in packs if p['name'] != pack_data['name']]
        packs.append(pack_data)
        self.save_modpacks_data(packs)
    
    def delete_modpack(self, name):
        packs = self.load_modpacks()
        packs = [p for p in packs if p['name'] != name]
        self.save_modpacks_data(packs)
        
        # Remove folder
        p_dir = os.path.join(self.packs_dir, name)
        if os.path.exists(p_dir):
            try: shutil.rmtree(p_dir)
            except: pass

    def scan_downloads_for_mod(self, mod_id, expected_file_name):
        home = os.path.expanduser("~")
        downloads = os.path.join(home, "Downloads")
        if not os.path.exists(downloads):
            downloads = os.path.join(home, "Transferências")
            if not os.path.exists(downloads):
                return None
        
        expected_root = expected_file_name.lower().rsplit('.', 1)[0]
        expected_clean = expected_root.replace(" ", "").replace("-", "").replace("_", "")
        
        now = time.time()
        for f in os.listdir(downloads):
            f_lower = f.lower()
            if f_lower.endswith(('.zip', '.jar')):
                if expected_root in f_lower or str(mod_id) in f:
                    path = os.path.join(downloads, f)
                    if now - os.path.getmtime(path) < 900: # 15 minutes
                        return path
                
                clean_f = f_lower.replace(" ", "").replace("-", "").replace("_", "")
                if expected_clean in clean_f:
                    path = os.path.join(downloads, f)
                    if now - os.path.getmtime(path) < 900:
                        return path
        return None
