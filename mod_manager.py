import os
import json
import time
import requests
import shutil
import zipfile
import sys
import subprocess
import threading
import psutil
from urllib.request import urlretrieve
import io
import struct
import logging

# Configure logging
logging.basicConfig(
    filename='map_gen.log',
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger("MapGen")

try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import zstandard as zstd
    HAS_ZSTD = True
except ImportError:
    HAS_ZSTD = False

class ModManager:
    def __init__(self):
        self.data_dir = os.path.join(os.getcwd(), "data")
        # Where we keep the "master" copy of all mods
        self.library_dir = os.path.join(self.data_dir, "library")
        # Where we keep modpack specific data like saves/configs
        self.packs_dir = os.path.join(self.data_dir, "packs")
        self.modpacks_file = os.path.join(self.data_dir, "modpacks.json")
        self.config_file = os.path.join(self.data_dir, "config.json")
        
        self.temp_backups_dir = os.path.join(self.data_dir, "temp_backups")
        
        for d in [self.data_dir, self.library_dir, self.packs_dir, self.temp_backups_dir]:
            if not os.path.exists(d):
                os.makedirs(d)
        
        self.config = self.load_config()
        if not self.config.get("game_dir"):
            detected = self.try_auto_detect_game()
            if detected:
                self.config['game_dir'] = detected
                self.save_config({})

        # Thread safety
        self.sync_lock = threading.Lock()
        self.is_launching = False

        self.base_url = "https://api.curseforge.com/v1"
        self.game_id = 70216

        if not os.path.exists(self.modpacks_file):
            with open(self.modpacks_file, 'w') as f:
                json.dump([], f)

        self.library_file = os.path.join(self.data_dir, "library.json")
        if not os.path.exists(self.library_file):
            with open(self.library_file, 'w') as f:
                json.dump({}, f)
        
        # Migration: Ensure all mods have internal IDs for save configs
        self.migrate_library_ids()

    def load_config(self):
        default = {
            "api_key": "",
            "game_dir": "",
            "manage_saves": False,
            "active_modpack": None
        }
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                data = json.load(f)
                default.update(data)
                return default
        return default

    def save_config(self, new_config):
        self.config.update(new_config)
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f)
        return {"status": "success"}

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
        """Attempts to find Hytale based on default paths provided by the user"""
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

    def get_headers(self):
        return {
            'x-api-key': self.config.get("api_key", ""),
            'Accept': 'application/json'
        }

    def launch_game(self, status_callback=None, console_callback=None):
        if self.is_launching:
            return {"status": "error", "message": "O jogo já está sendo iniciado."}
        
        self.is_launching = True
        try:
            # 0. Get active pack name for cleanup later
            active_pack = self.config.get("active_modpack")

            # 1. Sync Modpack first
            if status_callback: status_callback("Sincronizando...")
            sync_res = self.sync_modpack_to_game(callback=status_callback)
            if sync_res.get('status') == 'error':
                self.is_launching = False
                return sync_res

            game_path = self.config.get("game_dir")
            if not game_path:
                game_path = self.try_auto_detect_game()
                if not game_path:
                    self.is_launching = False
                    return {"status": "error", "message": "Por favor, configure o diretório ou executável do jogo nas configurações."}
            
            # Resolve ~ if present
            game_path = os.path.expanduser(game_path)
            
            if not os.path.exists(game_path):
                self.is_launching = False
                return {"status": "error", "message": f"O caminho configurado não existe: {game_path}"}

            target_exe = None
            # If path is a directory, search for the launcher
            if os.path.isdir(game_path):
                # Search Priority
                candidates = ["hytale-launcher", "HytaleLauncher.exe", "hytale-launcher.exe"]
                if sys.platform == 'win32':
                    candidates = ["HytaleLauncher.exe", "hytale-launcher.exe"]
                
                # Check root folder
                for c in candidates:
                    full_p = os.path.join(game_path, c)
                    if os.path.exists(full_p) and not os.path.isdir(full_p):
                        target_exe = full_p
                        break
                
                # Check /bin or similar if needed? Usually Hytale is flat.
                if not target_exe:
                    # Search recursively 1 level
                    for root, dirs, files in os.walk(game_path):
                        if root.count(os.sep) - game_path.count(os.sep) > 1: continue
                        for c in candidates:
                            full_p = os.path.join(root, c)
                            if os.path.exists(full_p) and not os.path.isdir(full_p):
                                target_exe = full_p
                                break
                        if target_exe: break
                    
                    if not target_exe:
                        self.is_launching = False
                        # Final fallback: opens folder
                        if sys.platform.startswith('linux'):
                            subprocess.Popen(['xdg-open', game_path])
                        elif sys.platform == 'win32':
                            os.startfile(game_path)
                        return {"status": "success", "info": "Pasta aberta (executável não encontrado)"}
            else:
                target_exe = game_path

            # Determine launch command
            is_flatpak = sys.platform.startswith('linux') and '.var/app/com.hypixel.HytaleLauncher' in target_exe
            
            if is_flatpak:
                print("Detectado Flatpak, usando 'flatpak run com.hypixel.HytaleLauncher'")
                cmd = ["flatpak", "run", "com.hypixel.HytaleLauncher"]
            else:
                if sys.platform != 'win32' and os.path.isfile(target_exe):
                    st = os.stat(target_exe)
                    os.chmod(target_exe, st.st_mode | 0o111)
                cmd = [target_exe]

            print(f"Lançando jogo via: {' '.join(cmd)}")
            if status_callback: status_callback("Iniciando Jogo...")
            
            # Launch with process output capture
            # Note: os.startfile on windows doesn't support capture, but we usually run via cmd on windows too if possible.
            # However, for now, we focus on Popen for proper capture.
            
            proc = subprocess.Popen(
                cmd, 
                cwd=os.path.dirname(target_exe), 
                env=os.environ.copy(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # Monitor in background
            def monitor():
                print("DEBUG: Monitor thread started")
                try:
                    # Capture output in real-time
                    if console_callback:
                        for line in iter(proc.stdout.readline, ""):
                            console_callback(line.strip())
                    
                    print("DEBUG: Waiting for launcher process")
                    proc.wait()
                    print("Launcher/Bridge closed. Checking for HytaleClient...")
                    
                    # 2. Polling for the game client
                    game_found = False
                    start_time = time.time()
                    while time.time() - start_time < 30: # 30s timeout for client start
                        for p in psutil.process_iter(['name']):
                            try:
                                if p.info['name'] == 'HytaleClient':
                                    game_found = True
                                    print("HytaleClient detected. Waiting for game to finish...")
                                    if status_callback: status_callback("playing")
                                    
                                    # Wait for client to exit
                                    p.wait()
                                    print("Game finished.")
                                    break
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                continue
                        if game_found: break
                        time.sleep(1)
                    
                    if not game_found:
                        print("Game client not detected within timeout.")
                    
                    # Cleanup
                    print("DEBUG: Cleanup started")
                    if active_pack:
                        self.cleanup_after_game(active_pack, callback=status_callback)
                    
                    self.is_launching = False
                    if status_callback: status_callback("finished")
                    print("DEBUG: Monitor finished")
                    
                except Exception as e:
                    print(f"Monitoring error: {e}")
                    self.is_launching = False

            threading.Thread(target=monitor, daemon=True).start()
            return {"status": "success", "message": "Iniciando..."}

        except Exception as e:
            self.is_launching = False
            return {"status": "error", "message": str(e)}

    def get_pack_logs(self, pack_name):
        """Discovers all log files across all saves in a pack"""
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
        
        # Sort by most recent
        all_logs.sort(key=lambda x: x['time'], reverse=True)
        return all_logs

    def read_log_file(self, pack_name, save_name, file_name):
        """Reads the content of a specific log file"""
        path = os.path.join(self.packs_dir, pack_name, "saves", save_name, "logs", file_name)
        if not os.path.exists(path): return "Arquivo não encontrado."
        
        try:
            # Logs can be big, limit to last 5000 lines or 1MB?
            # For simplicity, we read everything for now but you might want to slice.
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception as e:
            return f"Erro ao ler log: {e}"

    def cleanup_after_game(self, pack_name, callback=None):
        """Syncs saves back to modpack cache and clears game directory"""
        if not pack_name: return

        # Ensure only one cleanup runs at a time
        with self.sync_lock:
            game_dir = self.config.get("game_dir")
            if not game_dir or not os.path.exists(game_dir): return

            game_mods_dir = os.path.join(game_dir, "UserData", "Mods")
            game_saves_dir = self._get_saves_dir(game_dir)

            # 1. Sync Saves BACK to Modpack Cache (Progress Persistence)
            if self.config.get("manage_saves") and os.path.exists(game_saves_dir):
                if callback: callback("Sincronizando mundos (NEXCore -> Cache)...")
                pack_dir = os.path.join(self.packs_dir, pack_name)
                pack_saves_dir = os.path.join(pack_dir, "saves")
                
                try:
                    # Robust folder creation
                    if not os.path.exists(pack_dir): os.makedirs(pack_dir)
                    
                    if os.path.exists(pack_saves_dir): 
                        shutil.rmtree(pack_saves_dir)
                    
                    shutil.copytree(game_saves_dir, pack_saves_dir)
                    print(f"Saves synced back to pack: {pack_name}")
                except Exception as e:
                    print(f"Error syncing saves back: {e}")

            # 2. Delete Mods from Game Folder (Non-destructive)
            if callback: callback("Limpando arquivos temporários...")
            try:
                if os.path.exists(game_mods_dir):
                    self._clear_directory(game_mods_dir)
                    print("Game Mods folder cleared.")
            except Exception as e:
                print(f"Error clearing mods: {e}")

            # 3. Delete Saves from Game Folder (if managing saves) (Non-destructive)
            if self.config.get("manage_saves"):
                try:
                    if os.path.exists(game_saves_dir):
                        self._clear_directory(game_saves_dir)
                        print("Game Saves folder cleared.")
                except Exception as e:
                    print(f"Error clearing saves: {e}")

            # 4. Restore Original Game State (Pre-NEXCore Files)
            self._restore_original_game_state(game_mods_dir, game_saves_dir, callback=callback)

    def _backup_current_game_state(self, mods_dir, saves_dir, callback=None):
        """Backs up existing mods/saves from game folder to temp storage"""
        if callback: callback("Criando backup de segurança dos seus arquivos...")
        print("Iniciando backup temporário dos arquivos do jogo...")
        self._clear_directory(self.temp_backups_dir)
        
        try:
            # Backup Mods
            if os.path.exists(mods_dir) and os.listdir(mods_dir):
                dst = os.path.join(self.temp_backups_dir, "Mods")
                shutil.copytree(mods_dir, dst)
                print("Mods originais salvos em backup temporário.")
                
            # Backup Saves
            if os.path.exists(saves_dir) and os.listdir(saves_dir):
                dst = os.path.join(self.temp_backups_dir, "Saves")
                shutil.copytree(saves_dir, dst)
                print("Saves originais salvos em backup temporário.")
        except Exception as e:
            print(f"Erro ao criar backup temporário: {e}")

    def _restore_original_game_state(self, mods_dir, saves_dir, callback=None):
        """Restores files from temp storage back to game folder"""
        if callback: callback("Restaurando seus arquivos originais...")
        print("Restaurando arquivos originais do usuário...")
        
        try:
            # Restore Mods
            src_mods = os.path.join(self.temp_backups_dir, "Mods")
            if os.path.exists(src_mods):
                if not os.path.exists(mods_dir): os.makedirs(mods_dir)
                for item in os.listdir(src_mods):
                    s = os.path.join(src_mods, item)
                    d = os.path.join(mods_dir, item)
                    if os.path.isdir(s): shutil.copytree(s, d)
                    else: shutil.copy2(s, d)
                print("Mods originais restaurados.")

            # Restore Saves
            src_saves = os.path.join(self.temp_backups_dir, "Saves")
            if os.path.exists(src_saves):
                if not os.path.exists(saves_dir): os.makedirs(saves_dir)
                for item in os.listdir(src_saves):
                    s = os.path.join(src_saves, item)
                    d = os.path.join(saves_dir, item)
                    if os.path.isdir(s): shutil.copytree(s, d)
                    else: shutil.copy2(s, d)
                print("Saves originais restaurados.")
                
            # Clear temp after restore
            self._clear_directory(self.temp_backups_dir)
        except Exception as e:
            print(f"Erro ao restaurar arquivos originais: {e}")

    # --- API & Search ---
    def search_mods(self, query="", sort_field=1, sort_order="desc", offset=0):
        if not self.config.get("api_key"):
            return {"error": "API Key missing"}
        
        params = {
            'gameId': self.game_id,
            'searchFilter': query,
            'sortField': sort_field,
            'sortOrder': sort_order,
            'pageSize': 20,
            'index': offset
        }
        try:
            resp = requests.get(f"{self.base_url}/mods/search", headers=self.get_headers(), params=params)
            if resp.status_code == 200:
                data = resp.json().get('data', [])
                return self._inject_install_status(data)
            return {"error": resp.text}
        except Exception as e:
            return {"error": str(e)}

    def get_mod_description(self, mod_id):
        if not self.config.get("api_key"): return "API Key missing"
        try:
            resp = requests.get(f"{self.base_url}/mods/{mod_id}/description", headers=self.get_headers())
            return resp.json().get('data', "") if resp.status_code == 200 else "Descrição indisponível."
        except:
            return "Erro ao carregar descrição."

    def get_recommendations(self, preference=""):
        config = self.config
        if not config.get("api_key"): return {"error": "CurseForge API Key missing"}

        search_term = preference if preference else ""

        # --- Gemini Integration ---
        gemini_key = config.get("gemini_api_key")
        if gemini_key and preference:
            try:
                from google import genai
                client = genai.Client(api_key=gemini_key)
                
                model_name = config.get("gemini_model", "gemini-1.5-flash")
                
                prompt = f"Translate this mod preference into a single English keyword or very short phrase (max 2 words) for searching a Minecraft mod database. Return ONLY the keyword, nothing else. Preference: '{preference}'"
                
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                ai_term = response.text.strip()
                print(f"[AI Discovery] Gemini translated '{preference}' -> '{ai_term}'")
                search_term = ai_term
            except Exception as e:
                print(f"[AI Discovery] Gemini Error: {e}")
                # Fallback to original preference
        
        params = {
            'gameId': self.game_id,
            'searchFilter': search_term,
            'sortField': 2, # Popularity
            'sortOrder': 'desc',
            'pageSize': 50 
        }

    def export_modpack_cf(self, pack_name, target_path=None, progress_callback=None):
        """Exports a modpack in CurseForge format (manifest.json + overrides)"""
        logger.info(f"Exporting modpack '{pack_name}' to CurseForge format")
        if progress_callback: progress_callback(f"Iniciando exportação de {pack_name}...")
        
        # 1. Find the pack
        packs = self.load_modpacks()
        pack = next((p for p in packs if p['name'] == pack_name), None)
        if not pack:
            return {"status": "error", "message": f"Modpack '{pack_name}' não encontrado."}

        library = self.load_library()
        
        # 2. Build manifest.json
        manifest = {
            "minecraft": {
                "version": "Hytale", # Placeholder
                "modLoaders": [{"id": "hytale-core", "primary": True}]
            },
            "manifestType": "modpack",
            "manifestVersion": 1,
            "name": pack_name,
            "version": "1.0.0",
            "author": "NEXCore User",
            "files": [],
            "overrides": "overrides"
        }

        total_mods = len(pack['mods'])
        for i, mod_id in enumerate(pack['mods']):
            if progress_callback: progress_callback(f"Coletando metadados do mod {i+1}/{total_mods}...")
            mid_str = str(mod_id)
            file_id = None
            if mid_str in library and 'latest_file_id' in library[mid_str]:
                file_id = library[mid_str]['latest_file_id']
            else:
                try:
                    resp = requests.get(f"{self.base_url}/mods/{mod_id}", headers=self.get_headers())
                    if resp.status_code == 200:
                        mod_data = resp.json().get('data', {})
                        latest_files = mod_data.get('latestFiles', [])
                        if latest_files:
                            file_id = latest_files[0]['id']
                except: pass
            
            if file_id:
                manifest['files'].append({"projectID": mod_id, "fileID": file_id, "required": True})

        logger.info(f"Manifest ready with {len(manifest['files'])} mods. Starting ZIP creation.")
        if progress_callback: progress_callback("Gerando arquivo ZIP e incluindo arquivos (overrides)...")

        # 3. Create ZIP
        export_path = target_path if target_path else os.path.join(os.path.expanduser("~"), "Downloads", f"{pack_name}_CurseForge.zip")
        logger.info(f"Target export path: {export_path}")
        
        try:
            with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as z:
                z.writestr("manifest.json", json.dumps(manifest, indent=4))
                pack_dir = os.path.join(self.packs_dir, pack_name)
                if os.path.exists(pack_dir):
                    for root, dirs, files in os.walk(pack_dir):
                        # Filter out logs and backups directories
                        dirs[:] = [d for d in dirs if d not in ('logs', 'backups', 'backup')]
                        
                        for file in files:
                            if file == "map_preview.png": continue
                            file_full_path = os.path.join(root, file)
                            rel_path = os.path.relpath(file_full_path, pack_dir)
                            z.write(file_full_path, os.path.join("overrides", rel_path))
            
            logger.info("Export ZIP finalized successfully.")
            if progress_callback: progress_callback("Exportação concluída com sucesso!")
            return {"status": "success", "message": f"Modpack exportado para: {export_path}"}
        except Exception as e:
            logger.error(f"Error exporting modpack (ZIP PHASE): {e}", exc_info=True)
            return {"status": "error", "message": f"Erro ao criar ZIP: {str(e)}"}

    def import_modpack_cf(self, zip_path, progress_callback=None):
        """Imports a modpack from a CurseForge ZIP file"""
        logger.info(f"Importing modpack from CurseForge ZIP: {zip_path}")
        if progress_callback: progress_callback("Lendo manifesto do pacote...")
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as z:
                # 1. Read manifest.json
                if "manifest.json" not in z.namelist():
                    return {"status": "error", "message": "manifest.json não encontrado no ZIP."}
                
                manifest_data = z.read("manifest.json")
                manifest = json.loads(manifest_data)
                pack_name = manifest.get("name", "Imported Modpack")
                
                # Check for collisions
                packs = self.load_modpacks()
                if any(p['name'] == pack_name for p in packs):
                    pack_name = f"{pack_name}_{int(time.time())}"
                
                # 2. Download/Ensure mods
                files = manifest.get("files", [])
                total_mods = len(files)
                installed_mods = []
                manual_mods = []
                
                for i, mod_ref in enumerate(files):
                    mod_id = mod_ref['projectID']
                    if progress_callback:
                        progress_callback(f"Verificando mod {i+1}/{total_mods} (ID: {mod_id})...")
                    
                    library = self.load_library()
                    if str(mod_id) not in library:
                        try:
                            resp = requests.get(f"{self.base_url}/mods/{mod_id}", headers=self.get_headers())
                            if resp.status_code == 200:
                                mod_data = resp.json().get('data', {})
                                metadata = {
                                    "name": mod_data['name'],
                                    "slug": mod_data['slug'],
                                    "logo": mod_data.get('logo'),
                                    "summary": mod_data.get('summary')
                                }
                                # Install
                                install_res = self.install_mod_to_library(mod_id, metadata)
                                if install_res.get('status') == 'manual_required':
                                    manual_mods.append(install_res)
                        except Exception as e:
                            logger.error(f"Failed to process mod {mod_id}: {e}")
                    
                    installed_mods.append(mod_id)
                
                # 3. Create the Modpack directory and entry
                new_pack = {
                    "name": pack_name,
                    "mods": installed_mods,
                    "created": time.strftime("%Y-%m-%d")
                }
                packs.append(new_pack)
                with open(self.modpacks_file, 'w') as f:
                    json.dump(packs, f)
                
                # 4. Extract Overrides
                if progress_callback: progress_callback("Extraindo mundos e configurações (overrides)...")
                pack_dir = os.path.join(self.packs_dir, pack_name)
                os.makedirs(pack_dir, exist_ok=True)
                
                overrides_prefix = manifest.get("overrides", "overrides")
                for entry in z.namelist():
                    if entry.startswith(f"{overrides_prefix}/") and not entry.endswith("/"):
                        filename = entry[len(overrides_prefix)+1:]
                        target_path = os.path.join(pack_dir, filename)
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        with open(target_path, 'wb') as f:
                            f.write(z.read(entry))
                
                if progress_callback: progress_callback("Importação finalizada!")
                
                return {
                    "status": "success", 
                    "message": f"Modpack '{pack_name}' importado!",
                    "pack_name": pack_name,
                    "manual_mods": manual_mods # List of mods requiring manual download
                }
                
        except Exception as e:
            logger.error(f"Error importing modpack: {e}")
            return {"status": "error", "message": f"Erro na importação: {str(e)}"}
        
        try:
            resp = requests.get(f"{self.base_url}/mods/search", headers=self.get_headers(), params=params)
            if resp.status_code != 200: return {"error": resp.text}
            
            candidates = resp.json().get('data', [])
            
            library = self.load_library()
            installed_ids = list(str(k) for k in library.keys())
            
            recommendations = []
            for mod in candidates:
                if str(mod['id']) not in installed_ids:
                    recommendations.append(mod)
                    if len(recommendations) >= 5: break 
            
            # They are not installed by definition of the filter above, but let's be consistent
            # Actually get_recommendations explicitly filters out installed ones, so isInstalled is always False.
            # But just in case logic changes:
            return self._inject_install_status(recommendations)
            
        except Exception as e:
            return {"error": str(e)}

    def _inject_install_status(self, mods_list):
        library = self.load_library()
        installed_ids = set(str(k) for k in library.keys())
        for mod in mods_list:
            mod['isInstalled'] = str(mod['id']) in installed_ids
        return mods_list

    def get_mod_extended_info(self, mod_id):
        if not self.config.get("api_key"): return {}
        headers = self.get_headers()
        
        try:
            # 1. Get Mod Details (for Category)
            mod_resp = requests.get(f"{self.base_url}/mods/{mod_id}", headers=headers)
            if mod_resp.status_code != 200: return {}
            mod_data = mod_resp.json().get('data', {})
            
            # Categories
            categories = mod_data.get('categories', [])
            cat_id = categories[0].get('id') if categories else None
            
            # 2. Get Dependencies (from latest file)
            deps_data = []
            latest_files = mod_data.get('latestFiles', [])
            # Sort by date desc
            latest_files.sort(key=lambda x: x.get('fileDate', ''), reverse=True)
            
            if latest_files:
                # Find required dependencies
                req_deps_ids = []
                for dep in latest_files[0].get('dependencies', []):
                    if dep.get('relationType') == 3: # 3 = RequiredDependency
                        req_deps_ids.append(dep.get('modId'))
                
                # Bulk fetch dependency info
                if req_deps_ids:
                    headers['Content-Type'] = 'application/json'
                    dep_resp = requests.post(
                        f"{self.base_url}/mods", 
                        headers=headers, 
                        data=json.dumps({"modIds": req_deps_ids})
                    )
                    if dep_resp.status_code == 200:
                        deps_data = dep_resp.json().get('data', [])

            # 3. Similar Mods
            similar_data = []
            if cat_id:
                params = {
                    'gameId': self.game_id,
                    'categoryId': cat_id,
                    'sortField': 2, # Popularity
                    'sortOrder': 'desc',
                    'pageSize': 6
                }
                # Use requests.get fresh to avoid content-type conflict if any
                sim_resp = requests.get(f"{self.base_url}/mods/search", headers=self.get_headers(), params=params)
                if sim_resp.status_code == 200:
                    candidates = sim_resp.json().get('data', [])
                    for m in candidates:
                        if m['id'] != mod_id: # Exclude self
                            similar_data.append(m)
                            if len(similar_data) >= 5: break
            
            # Inject Install Status into the main mod info too
            mod_info = self._inject_install_status([mod_data])[0]

            return {
                "info": mod_info,
                "dependencies": self._inject_install_status(deps_data),
                "similar": self._inject_install_status(similar_data)
            }
            
        except Exception as e:
            print(f"Extended info error: {e}")
            return {"dependencies": [], "similar": []}

    def search_by_slug(self, slug):
        if not self.config.get("api_key"): return None
        # CurseForge allows searching by slug using 'slug' param on /mods/search?
        # Actually standard search often resolves slugs in 'searchFilter' or specific endpoint.
        # Let's try matching via search for now as specific slug endpoint is part of getMod, but we need ID first.
        # Wait, there is /v1/mods/search?slug={slug} ? No, usually it's searchFilter
        
        # Best bet: Search by term and filter locally or trust API ranking.
        # Better: use 'slug' parameter if available or 'searchFilter'.
        # According to CF API docs: parameter 'slug' exists!
        
        params = {
            'gameId': self.game_id,
            'slug': slug
        }
        try:
            resp = requests.get(f"{self.base_url}/mods/search", headers=self.get_headers(), params=params)
            if resp.status_code == 200:
                data = resp.json().get('data', [])
                if data:
                    return data[0]['id']
        except:
            pass
        return None

    def translate_html(self, html_content, target_lang="pt", callback=None):
        if not html_content: return ""
        
        # 1. Gemini Strategy (Best for preserving context and HTML structure)
        gemini_key = self.config.get("gemini_api_key")
        if gemini_key:
            try:
                from google import genai
                client = genai.Client(api_key=gemini_key)
                model_name = self.config.get("gemini_model", "gemini-1.5-flash")
                
                # Optimized prompt for HTML translation
                prompt = (
                    f"Translate the following HTML content to the language '{target_lang}'. "
                    "IMPORTANT: Preserve all HTML tags, attributes, and structure EXACTLY. "
                    "Only translate the user-visible text content. "
                    "Do not add any explanations or markdown code blocks (```html). "
                    "Just return the raw translated HTML.\n\n"
                    f"{html_content}"
                )
                
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                
                # Cleanup if model adds markdown blocks
                text = response.text.strip()
                if text.startswith("```html"): text = text[7:]
                if text.startswith("```"): text = text[3:]
                if text.endswith("```"): text = text[:-3]
                
                translated_final = text.strip()
                if callback: callback(translated_final)
                return translated_final
            except Exception as e:
                print(f"Gemini Translation Error: {e}")
                # Fallback to free translator
        
        # 2. Free Translator Strategy (Deep Translator + BeautifulSoup)
        try:
            from bs4 import BeautifulSoup, NavigableString
            from deep_translator import GoogleTranslator
            
            soup = BeautifulSoup(html_content, 'html.parser')
            translator = GoogleTranslator(source='auto', target=target_lang)
            
            # Mapping valid target codes for DeepTranslator/Google
            if target_lang.lower() in ['pt-br', 'pt_br']: target_lang = 'pt'
            
            last_update_time = 0
            
            # Limit element traversal to avoid translating scripts/styles
            for element in soup.descendants:
                if isinstance(element, NavigableString):
                    if element.parent.name in ['script', 'style', 'code', 'pre']:
                        continue
                        
                    original_text = str(element).strip()
                    if len(original_text) > 2: # heuristic to skip symbols
                        try:
                            translated = translator.translate(original_text, target=target_lang)
                            if translated:
                                element.replace_with(translated)
                                
                                # Push update to frontend every 1s or so to avoid flickering
                                if callback and (time.time() - last_update_time > 0.8):
                                    callback(str(soup))
                                    last_update_time = time.time()
                        except Exception as e:
                            print(f"Translation chunk error: {e}")
            
            final_soup = str(soup)
            if callback: callback(final_soup)
            return final_soup
            
        except ImportError:
            return "Erro: Bibliotecas não instaladas (bs4/deep-translator)."
        except Exception as e:
            return f"Erro na tradução gratuita: {str(e)}"

    # --- Core Logic ---
        self.library_file = os.path.join(self.data_dir, "library.json")
        if not os.path.exists(self.library_file):
            with open(self.library_file, 'w') as f:
                json.dump({}, f)

    def load_library(self):
        try:
            with open(self.library_file, 'r') as f:
                return json.load(f)
        except:
            return {}

    def save_library(self, lib_data):
        with open(self.library_file, 'w') as f:
            json.dump(lib_data, f)

    def get_mod_info(self, mod_id):
        lib = self.load_library()
        return lib.get(str(mod_id)) or lib.get(int(mod_id))

    # --- Core Logic ---
    def fetch_mod_metadata(self, mod_id):
        if not self.config.get("api_key"): return None
        try:
            resp = requests.get(f"{self.base_url}/mods/{mod_id}", headers=self.get_headers())
            if resp.status_code == 200:
                data = resp.json().get('data', {})
                # Update library if it exists there
                lib = self.load_library()
                mid_str = str(mod_id)
                
                # We either update or just return the info
                info = {
                    "name": data.get("name"),
                    "slug": data.get("slug"),
                    "logo": data.get("logo", {}),
                    "summary": data.get("summary", ""),
                    "links": data.get("links", {}),
                    "file_name": lib.get(mid_str, {}).get("file_name", f"{mod_id}.zip")
                }
                
                if mid_str in lib:
                    lib[mid_str].update(info)
                    self.save_library(lib)
                
                return info
            return None
        except:
            return None

    def install_mod_to_library(self, mod_id, mod_metadata=None, processed_ids=None):
        """Downloads mod to library and recursively installs required dependencies"""
        if processed_ids is None: processed_ids = set()
        
        mod_id_str = str(mod_id)
        if mod_id_str in processed_ids: return {"status": "success", "message": "Já processado"}
        processed_ids.add(mod_id_str)

        if not self.config.get("api_key"): return {"status": "error", "message": "No API Key"}

        try:
            # 1. Fetch File Info to get dependencies
            files_resp = requests.get(
                f"{self.base_url}/mods/{mod_id}/files",
                headers=self.get_headers(),
                params={'pageSize': 1, 'sortOrder': 'desc'}
            )
            files_data = files_resp.json().get('data', [])
            if not files_data: return {"status": "error", "message": "No files found"}
            
            target_file = files_data[0]
            download_url = target_file.get('downloadUrl')
            # Use fileName from API if available, fallback to displayName or modId.zip
            file_name = target_file.get('fileName') or target_file.get('displayName', f"{mod_id}.zip")

            # 2. Handle Dependencies Recursively
            deps = target_file.get('dependencies', [])
            dep_count = 0
            for dep in deps:
                # 3 = RequiredDependency
                if dep.get('relationType') == 3:
                    dep_id = dep.get('modId')
                    # Recursively install dependency
                    # We don't have metadata for it yet, so let it fetch on the fly if needed
                    self.install_mod_to_library(dep_id, processed_ids=processed_ids)
                    dep_count += 1

            # 3. Download the main mod file
            dest_path = os.path.join(self.library_dir, file_name)
            
            if not os.path.exists(dest_path):
                if not download_url:
                     # This happens when authors disable 3rd party API downloads on CurseForge
                     print(f"[Warning] Download URL is None for mod {mod_id}")
                     
                     # Fetch full mod data if not provided to get the slug
                     slug = ""
                     if mod_metadata and mod_metadata.get('slug'):
                         slug = mod_metadata.get('slug')
                     else:
                         mod_resp = requests.get(f"{self.base_url}/mods/{mod_id}", headers=self.get_headers())
                         if mod_resp.status_code == 200:
                             mod_data = mod_resp.json().get('data', {})
                             slug = mod_data.get('slug', "")
                     
                     file_id = target_file.get('id')
                     # Direct Download URL pattern: https://www.curseforge.com/hytale/mods/{slug}/download/{fileId}
                     manual_url = f"https://www.curseforge.com/hytale/mods/{slug}/download/{file_id}" if slug else "https://www.curseforge.com/hytale/mods"

                     return {
                         "status": "manual_required", 
                         "message": "Download negado pela API. O autor exige download manual.",
                         "url": manual_url,
                         "file_name": file_name,
                         "mod_id": mod_id
                     }

                urlretrieve(download_url, dest_path)
            
            # 4. Save/Update Metadata
            # If no metadata provided (common for auto-installed deps), fetch it
            if not mod_metadata:
                mod_metadata = self.fetch_mod_metadata(mod_id)
            
            if mod_metadata:
                lib = self.load_library()
                internal_id = self._extract_internal_id(dest_path)
                lib[mod_id_str] = {
                    "name": mod_metadata.get("name", "Unknown"),
                    "internal_id": internal_id or "Unknown:Unknown",
                    "logo": mod_metadata.get("logo", {}),
                    "summary": mod_metadata.get("summary", ""),
                    "file_name": file_name
                }
                self.save_library(lib)
            
            # 5. Automatic Linking to Active Modpack
            active_pack = self.config.get("active_modpack")
            linked_msg = ""
            
            if active_pack:
                self.add_mod_to_pack(active_pack, mod_id)
                linked_msg = f" & vinculado a '{active_pack}'"

            msg = "Instalado"
            if dep_count > 0:
                msg = f"Instalado com {dep_count} dependências"
                
            return {"status": "success", "file_name": file_name, "message": f"{msg}{linked_msg}"}
        except Exception as e:
            print(f"Install error ({mod_id}): {e}")
            return {"status": "error", "message": str(e)}

    def delete_mod_from_library(self, mod_id):
        # 1. Load data
        lib = self.load_library()
        mod_id_str = str(mod_id)
        info = lib.get(mod_id_str)
        
        if not info:
            return {"status": "error", "message": "Mod não encontrado na biblioteca."}

        # 2. Remove physical file
        file_name = info.get("file_name")
        if file_name:
            file_path = os.path.join(self.library_dir, file_name)
            if os.path.exists(file_path):
                os.remove(file_path)

        # 3. Remove from library.json
        del lib[mod_id_str]
        self.save_library(lib)

        # 4. Remove from all modpacks (Robust string-based comparison)
        with open(self.modpacks_file, 'r') as f:
            packs = json.load(f)
        
        for pack in packs:
            pack['mods'] = [m for m in pack.get('mods', []) if str(m) != mod_id_str]
        
        with open(self.modpacks_file, 'w') as f:
            json.dump(packs, f)

        # 5. If active in game folder, remove it
        game_dir = self.config.get("game_dir")
        if game_dir and file_name:
            # Default Hytale mods path
            game_mods_dir = os.path.join(game_dir, "UserData", "Mods")
            path_in_game = os.path.join(game_mods_dir, file_name)
            if os.path.exists(path_in_game):
                os.remove(path_in_game)
            # Also check if it was extracted (zip)
            extracted_dir = os.path.join(game_mods_dir, os.path.splitext(file_name)[0])
            if os.path.exists(extracted_dir):
                shutil.rmtree(extracted_dir)

        return {"status": "success"}

    def delete_modpack(self, name):
        # 1. Remove from JSON
        with open(self.modpacks_file, 'r') as f:
            packs = json.load(f)
        
        new_packs = [p for p in packs if p['name'] != name]
        
        with open(self.modpacks_file, 'w') as f:
            json.dump(new_packs, f)
        
        # 2. Remove Folder
        pack_folder = os.path.join(self.packs_dir, name)
        if os.path.exists(pack_folder):
            shutil.rmtree(pack_folder)
            
        # 3. Unset active if needed
        if self.config.get("active_modpack") == name:
            self.config['active_modpack'] = None
            self.save_config({})
            
        return {"status": "success"}

    def save_modpack(self, name, mod_ids):
        with open(self.modpacks_file, 'r') as f:
            packs = json.load(f)
            
        # Check if updating existing
        existing = next((p for p in packs if p['name'] == name), None)
        if existing:
            existing['mods'] = mod_ids
        else:
            packs.append({"name": name, "mods": mod_ids, "created": time.strftime("%Y-%m-%d")})
        
        with open(self.modpacks_file, 'w') as f:
            json.dump(packs, f)
        
        # Create pack folder
        pack_folder = os.path.join(self.packs_dir, name)
        if not os.path.exists(pack_folder):
             os.makedirs(os.path.join(pack_folder, "saves"))

        return {"status": "success"}

    def activate_modpack(self, pack_name):
        """Selection is now instant. Deployment happens at launch_game."""
        with open(self.modpacks_file, 'r') as f:
            packs = json.load(f)
        target_pack = next((p for p in packs if p['name'] == pack_name), None)
        
        if not target_pack: 
            return {"status": "error", "message": "Modpack not found"}

        # Simply update config
        self.config['active_modpack'] = pack_name
        self.save_config({})
        return {"status": "success"}

    def _clear_directory(self, path):
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

    def _get_saves_dir(self, game_dir):
        """Finds the correct saves directory (standardizing on 'Saves' for Linux/NEXCore)"""
        p_upper = os.path.join(game_dir, "UserData", "Saves")
        p_lower = os.path.join(game_dir, "UserData", "saves")
        
        # If we have the lowercase one but not the uppercase, rename it to standardize
        if os.path.exists(p_lower) and not os.path.exists(p_upper):
            try:
                os.rename(p_lower, p_upper)
            except:
                pass
        
        # If both exist and lowercase is empty, remove lowercase
        if os.path.exists(p_lower) and os.path.exists(p_upper):
            try:
                if not os.listdir(p_lower):
                    os.rmdir(p_lower)
            except:
                pass

        return p_upper

    def sync_modpack_to_game(self, callback=None):
        """Performs actual file transfers (Mods & Saves) for the active modpack"""
        game_dir = self.config.get("game_dir")
        pack_name = self.config.get("active_modpack")
        
        if not game_dir or not os.path.exists(game_dir):
            return {"status": "error", "message": "Diretório do jogo inválido."}
        if not pack_name:
            return {"status": "success", "info": "Nenhum modpack ativo para sincronizar."}

        # UserData folders
        game_mods_dir = os.path.join(game_dir, "UserData", "Mods")
        game_saves_dir = self._get_saves_dir(game_dir)

        # 0. Backup current state before anything
        self._backup_current_game_state(game_mods_dir, game_saves_dir, callback=callback)

        # 1. Clear & Deploy Mods (Non-destructive)
        if callback: callback("Limpando pasta de mods...")
        if not os.path.exists(game_mods_dir): os.makedirs(game_mods_dir)
        self._clear_directory(game_mods_dir)

        with open(self.modpacks_file, 'r') as f:
            packs = json.load(f)
        target_pack = next((p for p in packs if p['name'] == pack_name), None)
        if not target_pack: return {"status": "error", "message": "Pack config gone"}

        errors = []
        mods_list = target_pack.get('mods', [])
        total_mods = len(mods_list)
        
        for i, mod_id in enumerate(mods_list):
            if callback: callback(f"Sincronizando mod {i+1}/{total_mods}...")
            
            res = self.install_mod_to_library(mod_id)
            if res['status'] == 'success' or res['status'] == 'manual_required':
                 f_name = res.get('file_name')
                 if not f_name: continue
                 
                 src = os.path.join(self.library_dir, f_name)
                 dst = os.path.join(game_mods_dir, f_name)
                 if os.path.exists(src):
                    if f_name.endswith('.zip'):
                        extract_to = os.path.join(game_mods_dir, os.path.splitext(f_name)[0])
                        if os.path.exists(extract_to):
                            if os.path.isdir(extract_to): shutil.rmtree(extract_to)
                            else: os.remove(extract_to)
                        
                        with zipfile.ZipFile(src, 'r') as z:
                            z.extractall(extract_to)
                    else:
                        shutil.copy2(src, dst)
            else:
                errors.append(f"Mod {mod_id} missing")

        # 3. Deploy Saves (Non-destructive)
        if self.config.get("manage_saves"):
            if callback: callback("Sincronizando Saves...")
            if not os.path.exists(game_saves_dir): os.makedirs(game_saves_dir)
            self._clear_directory(game_saves_dir)
            
            target_saves = os.path.join(self.packs_dir, pack_name, "saves")
            if os.path.exists(target_saves):
                # Copy contents, excluding logs and backups for deployment
                for item in os.listdir(target_saves):
                    if item.lower() in ('logs', 'backups', 'backup'): continue
                    
                    s = os.path.join(target_saves, item)
                    d = os.path.join(game_saves_dir, item)
                    if os.path.isdir(s):
                        shutil.copytree(s, d)
                    else:
                        shutil.copy2(s, d)
        
        return {"status": "success", "errors": errors}

    def get_modpack_details(self, pack_name):
        with open(self.modpacks_file, 'r') as f:
            packs = json.load(f)
        
        target = next((p for p in packs if p['name'] == pack_name), None)
        if not target: return {"error": "Not found"}

        lib = self.load_library()
        rich_mods = []
        ghost_ids = []
        for mid in target.get('mods', []):
            info = lib.get(str(mid)) or lib.get(int(mid))
            if not info:
                # Try to heal on the fly
                info = self.fetch_mod_metadata(mid)
            
            if info:
                rich_mods.append({
                    "id": mid,
                    "name": info.get("name"),
                    "internal_id": info.get("internal_id", "Unknown:Unknown"),
                    "logo": info.get("logo"),
                    "summary": info.get("summary")
                })
        if ghost_ids:
            # Clean up modpacks.json permanently
            target['mods'] = [m for m in target['mods'] if m not in ghost_ids]
            with open(self.modpacks_file, 'w') as f:
                json.dump(packs, f)
            print(f"[Cleanup] Removed {len(ghost_ids)} ghost mods from pack '{pack_name}'")
        
        return {"name": target['name'], "mods": rich_mods, "created": target.get('created')}

    def get_saves_for_pack(self, pack_name):
        saves_dir = os.path.join(self.packs_dir, pack_name, "saves")
        if not os.path.exists(saves_dir):
            return []
        
        saves = []
        try:
            for d in os.listdir(saves_dir):
                path = os.path.join(saves_dir, d)
                if os.path.isdir(path):
                    info = self._get_save_info(path)
                    if info:
                        info['folder_name'] = d
                        saves.append(info)
        except Exception as e:
            print(f"Error listing saves: {e}")
            
        return saves

    def _get_save_info(self, save_path):
        # 1. Mod Config (Root config.json)
        config_path = os.path.join(save_path, "config.json")
        mods_config = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    mods_config = json.load(f).get("Mods", {})
            except: pass

        # 2. World Config (Universe)
        world_config_path = os.path.join(save_path, "universe", "worlds", "default", "config.json")
        world_info = {"name": os.path.basename(save_path)} # Fallback
        
        if os.path.exists(world_config_path):
            try:
                with open(world_config_path, 'r') as f:
                    wi = json.load(f)
                    world_info = {
                        "name": wi.get("DisplayName", os.path.basename(save_path)),
                        "seed": wi.get("Seed"),
                        "gamemode": wi.get("GameMode"),
                        "pvp": wi.get("IsPvpEnabled"),
                        "fall_damage": wi.get("IsFallDamageEnabled")
                    }
            except: pass
        # 3. Preview
        preview_path = os.path.join(save_path, "preview.png")
        has_preview = os.path.exists(preview_path)

        return {
            "world": world_info,
            "mods": mods_config,
            "has_preview": has_preview
        }

    def update_save(self, pack_name, folder_name, config):
        save_path = os.path.join(self.packs_dir, pack_name, "saves", folder_name)
        if not os.path.exists(save_path):
            return {"status": "error", "message": "Save folder not found"}

        try:
            # 1. Update Mods (Root config.json)
            if "mods" in config:
                config_path = os.path.join(save_path, "config.json")
                # Format: {"Mods": {"Name": {"Enabled": bool}}}
                with open(config_path, 'w') as f:
                    json.dump({"Mods": config['mods']}, f, indent=2)

            # 2. Update World Settings (Universe)
            world_config_path = os.path.join(save_path, "universe", "worlds", "default", "config.json")
            if os.path.exists(world_config_path):
                with open(world_config_path, 'r') as f:
                    wi = json.load(f)
                
                if "name" in config: wi["DisplayName"] = config["name"]
                
                # Handle Seed conversion (could be empty string from UI)
                seed_val = config.get("seed")
                if seed_val is not None and str(seed_val).strip() != "":
                    try:
                        wi["Seed"] = int(seed_val)
                    except: pass
                
                if "gamemode" in config: 
                    gm = config["gamemode"]
                    if gm == "Survival": gm = "Adventure"
                    wi["GameMode"] = gm
                if "pvp" in config: wi["IsPvpEnabled"] = config["pvp"]
                if "fall_damage" in config: wi["IsFallDamageEnabled"] = config["fall_damage"]

                with open(world_config_path, 'w') as f:
                    json.dump(wi, f, indent=2)

            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def delete_save(self, pack_name, folder_name):
        save_path = os.path.join(self.packs_dir, pack_name, "saves", folder_name)
        if os.path.exists(save_path):
            try:
                shutil.rmtree(save_path)
                return {"status": "success"}
            except Exception as e:
                return {"status": "error", "message": str(e)}
        return {"status": "error", "message": "Save not found"}

    def create_save(self, pack_name, config):
        folder_name = config.get("name", "New_World").replace(" ", "_")
        saves_dir = os.path.join(self.packs_dir, pack_name, "saves")
        if not os.path.exists(saves_dir): os.makedirs(saves_dir)
        
        # Ensure unique folder name
        base_folder = folder_name
        counter = 1
        while os.path.exists(os.path.join(saves_dir, folder_name)):
            folder_name = f"{base_folder}_{counter}"
            counter += 1
            
        save_path = os.path.join(saves_dir, folder_name)
        
        try:
            # 1. Create Folder Structure
            os.makedirs(os.path.join(save_path, "universe", "worlds", "default", "resources"))
            os.makedirs(os.path.join(save_path, "logs"))
            os.makedirs(os.path.join(save_path, "mods"))
            
            # 2. client_metadata.json
            with open(os.path.join(save_path, "client_metadata.json"), 'w') as f:
                json.dump({"CreatedWithPatchline": "release"}, f)
            
            # 3. Root config.json (Mods)
            # Default: enable all mods from the pack if not specified
            mods_payload = config.get("mods", {})
            with open(os.path.join(save_path, "config.json"), 'w') as f:
                json.dump({"Mods": mods_payload}, f, indent=2)

            # 4. World config.json
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%S.000000000Z", time.gmtime())
            
            # Handle Seed fallback
            raw_seed = config.get("seed")
            final_seed = int(time.time() * 1000)
            if raw_seed is not None and str(raw_seed).strip() != "":
                try:
                    final_seed = int(raw_seed)
                except: pass

            # Internal GameMode mapping: Hytale uses 'Adventure' for survival
            gm = config.get("gamemode", "Adventure")
            if gm == "Survival": gm = "Adventure"

            world_config = {
                "Version": 4,
                "DisplayName": config.get("name", "New World"),
                "Seed": final_seed,
                "GameMode": gm,
                "IsPvpEnabled": config.get("pvp", False),
                "IsFallDamageEnabled": config.get("fall_damage", True),
                "WorldGen": {"Type": "Hytale", "Name": "Default"},
                "WorldMap": {"Type": "WorldGen"},
                "ChunkStorage": {"Type": "Hytale"},
                "IsTicking": True,
                "IsBlockTicking": True,
                "IsSpawningNPC": True,
                "IsSavingPlayers": True,
                "IsSavingChunks": True,
                "SaveNewChunks": True,
                "GameTime": now_iso,
                "ResourceStorage": {"Type": "Hytale"}
            }
            with open(os.path.join(save_path, "universe", "worlds", "default", "config.json"), 'w') as f:
                json.dump(world_config, f, indent=2)

            return {"status": "success", "folder_name": folder_name}
        except Exception as e:
            if os.path.exists(save_path): shutil.rmtree(save_path)
            return {"status": "error", "message": str(e)}

    def remove_mod_from_pack(self, pack_name, mod_id):
        # 1. Update JSON
        with open(self.modpacks_file, 'r') as f:
            packs = json.load(f)
        
        target = next((p for p in packs if p['name'] == pack_name), None)
        if not target: return {"status": "error"}

        # convert to int/str consistency
        mod_id = int(mod_id)
        if mod_id in target['mods']:
            target['mods'].remove(mod_id)
        
        with open(self.modpacks_file, 'w') as f:
            json.dump(packs, f)

        # 2. If Active, remove from game folder (Hot Remove)
        if self.config.get("active_modpack") == pack_name:
            # We need the filename.
            info = self.get_mod_info(mod_id)
            if info:
                fname = info.get("file_name")
                game_dir = self.config.get("game_dir")
                if fname and game_dir:
                    game_mods_dir = os.path.join(game_dir, "UserData", "Mods")
                    p = os.path.join(game_mods_dir, fname)
                    if os.path.exists(p): 
                        if os.path.isdir(p): shutil.rmtree(p)
                        else: os.remove(p)
                    
                    # Also zip folder if exists (compat with old logic)
                    pz = os.path.join(game_mods_dir, os.path.splitext(fname)[0])
                    if os.path.exists(pz): shutil.rmtree(pz)

        return {"status": "success"}


    def generate_world_map(self, pack_name, save_name):
        """Generates a map preview based on explored chunks and asset colors (Experimental v2)"""
        logger.info(f"Starting map generation for {pack_name} / {save_name}")
        
        if not HAS_PIL: 
            logger.error("Pillow not installed")
            return {"status": "error", "message": "Pillow not installed"}
        if not HAS_ZSTD: 
            logger.error("zstandard not installed")
            return {"status": "error", "message": "zstandard not installed"}
            
        save_path = os.path.join(self.packs_dir, pack_name, "saves", save_name)
        worlds_dir = os.path.join(save_path, "universe", "worlds")
        
        if not os.path.exists(worlds_dir):
            logger.error(f"Worlds directory not found: {worlds_dir}")
            return {"status": "error", "message": "Save structure invalid (no worlds folder)"}

        # Find the main world
        target_world = None
        max_chunks = -1
        
        for w in os.listdir(worlds_dir):
            w_path = os.path.join(worlds_dir, w)
            c_path = os.path.join(w_path, "chunks")
            if os.path.exists(c_path):
                count = len(os.listdir(c_path))
                if count > max_chunks:
                    max_chunks = count
                    target_world = w_path
        
        if not target_world:
             logger.error("No worlds with chunks found")
             return {"status": "error", "message": "No chunks found"}

        logger.info(f"Target world identified: {os.path.basename(target_world)} with {max_chunks} region files")

        chunks_dir = os.path.join(target_world, "chunks")
        region_files = [f for f in os.listdir(chunks_dir) if f.endswith(".region.bin")]
        
        if not region_files:
            logger.error("No .region.bin files found")
            return {"status": "error", "message": "No region files"}

        # Coordinate min/max
        min_x, min_z = 99999, 99999
        max_x, max_z = -99999, -99999
        
        valid_regions = []
        for rf in region_files:
            try:
                parts = rf.split('.')
                rx = int(parts[0])
                rz = int(parts[1])
                valid_regions.append((rx, rz, os.path.join(chunks_dir, rf)))
                min_x = min(min_x, rx)
                min_z = min(min_z, rz)
                max_x = max(max_x, rx)
                max_z = max(max_z, rz)
            except: pass
            
        if not valid_regions:
            logger.error("No valid region coordinates parsed")
            return {"status": "error", "message": "No valid regions"}

        logger.info(f"Region Bounds: X({min_x} to {max_x}), Z({min_z} to {max_z})")

        # Canvas Size
        width_chunks = (max_x - min_x + 1) * 32
        height_chunks = (max_z - min_z + 1) * 32
        
        MAX_RES = 2048
        scale = 1
        if width_chunks > MAX_RES or height_chunks > MAX_RES:
            scale = 32 # effectively 1 pixel per region
            width_chunks = (max_x - min_x + 1)
            height_chunks = (max_z - min_z + 1)

        logger.info(f"Map Canvas Size: {width_chunks}x{height_chunks} (Scale: {scale})")

        img = Image.new('RGB', (width_chunks, height_chunks), color=(20, 20, 25))
        pixels = img.load()
        
        # Load palette
        palette_path = os.path.join(self.data_dir, "block_colors.json")
        palette = {}
        if os.path.exists(palette_path):
            with open(palette_path, 'r') as f:
                raw_palette = json.load(f)
                # Ensure all keys are lowercase and values are TUPLES for PIL
                palette = {k.lower(): tuple(v) for k, v in raw_palette.items()}
            logger.info(f"Loaded palette with {len(palette)} entries")
        else:
            logger.warning(f"Palette file not found at {palette_path}")

        # Pre-compute encoded palette keys for faster lookup
        # Hytale uses Title_Case in NBT (Rock_Bedrock, Ore_Iron_Basalt)
        # but palette has lowercase keys. We need both versions.
        palette_keys_encoded = {}
        for k in palette.keys():
            # Add lowercase version
            palette_keys_encoded[k] = k.encode('utf-8')
            # Add Title_Case version (capitalize each part after _)
            title_case = '_'.join(word.capitalize() for word in k.split('_'))
            palette_keys_encoded[k + '_title'] = title_case.encode('utf-8')

        for rx, rz, rf_path in valid_regions:
            logger.debug(f"Processing region {rx}.{rz}...")
            try:
                with open(rf_path, 'rb') as f:
                    content = f.read()
                    
                    table_data = content[40:40+4096]
                    if len(table_data) < 4096: 
                        logger.warning(f"Region {rx}.{rz} has truncated header table")
                        continue
                    chunk_offsets = struct.unpack('>1024I', table_data)
                    
                    valid_offsets = [o for o in chunk_offsets if 0 < o < 1000000]
                    # Log only if significant
                    if len(valid_offsets) > 0:
                        logger.debug(f"Region {rx}.{rz}: Found {len(valid_offsets)} non-zero chunk offsets")

                    dctx = zstd.ZstdDecompressor()
                    rg_off_x = (rx - min_x) * (32 // scale)
                    rg_off_z = (rz - min_z) * (32 // scale)

                    # Block priorities for "Top-Down" view (higher = more visible)
                    PRIORITIES = {
                        "water": 100, "lava": 99, "snow": 90,
                        "grass": 85, "vegetation": 84, "flower": 83,
                        "sand": 75, "gravel": 74,
                        "leaves": 65, "tree": 64,
                        "log": 55, "wood": 54,
                        "ore": 45,
                        "dirt": 35, "soil": 34,
                        "clay": 25,
                        "rock": 15, "stone": 12, "volcanic": 11,
                        "bedrock": 1
                    }

                    for grid_idx, block_idx in enumerate(chunk_offsets):
                        if block_idx == 0 or block_idx > 1000000: continue
                        
                        # CORRECT FORMULA: Sector 0 starts at byte 40 (Table Start)
                        byte_off = 40 + block_idx * 4096
                        if byte_off >= len(content): continue
                        
                        try:
                            # Verify ZSTD magic before decompressing
                            if content[byte_off:byte_off+4] != b'\x28\xb5\x2f\xfd':
                                # Fallback: Maybe it's at the +8 offset some regions have?
                                if byte_off + 8 < len(content) and content[byte_off+8:byte_off+12] == b'\x28\xb5\x2f\xfd':
                                    byte_off += 8
                                else:
                                    continue
                            # We need to decompress. Zstandard can take a larger buffer 
                            # and will stop at frame end but we specify a max output size
                            with dctx.stream_reader(io.BytesIO(content[byte_off:])) as reader:
                                cdata = reader.read(65536)
                                
                                # NOVA ABORDAGEM: Buscar diretamente por nomes da paleta
                                best_color = None
                                best_priority = -1
                                match_count = 0
                                matched_blocks = []
                                
                                # Procurar cada nome de bloco da paleta no chunk
                                for key_name, encoded_key in palette_keys_encoded.items():
                                    if encoded_key in cdata:
                                        # Remove suffix '_title' se presente
                                        palette_key = key_name.replace('_title', '') if '_title' in key_name else key_name
                                        
                                        # Evitar contar duplicatas (lowercase + Title_Case do mesmo bloco)
                                        if palette_key in matched_blocks:
                                            continue
                                        matched_blocks.append(palette_key)
                                        
                                        match_count += 1
                                        color_val = palette[palette_key]
                                        
                                        if best_color is None:
                                            best_color = color_val
                                            
                                        priority = 20
                                        for key, p_val in PRIORITIES.items():
                                            if key in palette_key:
                                                priority = p_val
                                                break
                                        
                                        if priority > best_priority:
                                            best_priority = priority
                                            best_color = color_val
                                
                                # Fallback: Se nenhum bloco foi encontrado, usar cinza médio
                                # (chunks vazios/subterrâneos ou blocos não mapeados)
                                color = best_color if best_color else (60, 60, 65)
                                
                                # Debug logging para primeiros chunks
                                if grid_idx % 100 == 0 and grid_idx > 0:
                                    logger.debug(f"Chunk {grid_idx} (Region {rx}.{rz}): Found {match_count} blocks in palette")

                                # Use grid index to calculate relative position within region
                                # grid_idx is the chunk index within the 32x32 region grid (0-1023)
                                # Row-major ordering: first 32 chunks are row 0, next 32 are row 1, etc.
                                local_x = grid_idx % 32   # X position within region (0-31)
                                local_z = grid_idx // 32  # Z (row) position within region (0-31)
                                
                                # Add region offset and scale
                                px = rg_off_x + (local_x // scale)
                                pz = rg_off_z + (local_z // scale)

                                # Bounds check
                                if 0 <= px < width_chunks and 0 <= pz < height_chunks:
                                    # Ensure color is a tuple of 3 ints
                                    if isinstance(color, (list, tuple)) and len(color) >= 3:
                                        pixels[px, pz] = tuple(int(c) for c in color[:3])
                                    else:
                                        pixels[px, pz] = (60, 60, 65)
                        except Exception as e:
                            if grid_idx == 0: # Only log first error to avoid massive logs if decompression fails
                                logger.error(f"Decompression error in chunk {grid_idx} of region {rx}.{rz}: {e}")
            except Exception as e:
                logger.error(f"Error reading region {rx}.{rz}: {e}")
                continue

        out_path = os.path.join(save_path, "map_preview.png")
        final_img = img
        if width_chunks < 1024:
             target_w = max(512, width_chunks)
             target_h = max(512, height_chunks)
             final_img = img.resize((target_w, target_h), Image.NEAREST)
        
        final_img.save(out_path)
        logger.info(f"Map generation finished. Saved to {out_path}")
        return {"status": "success", "path": out_path}


    def add_mod_to_pack(self, pack_name, mod_id):
        # 1. Update JSON
        with open(self.modpacks_file, 'r') as f:
            packs = json.load(f)
        
        target = next((p for p in packs if p['name'] == pack_name), None)
        if not target: return {"status": "error", "message": "Pack not found"}
        
        mod_id = int(mod_id)
        if mod_id not in target['mods']:
            target['mods'].append(mod_id)
            with open(self.modpacks_file, 'w') as f:
                json.dump(packs, f)
        
        # 2. If active, deploy
        if self.config.get("active_modpack") == pack_name:
            info = self.get_mod_info(mod_id)
            if info:
                f_name = info.get("file_name")
                game_dir = self.config.get("game_dir")
                if f_name and game_dir:
                     game_mods_dir = os.path.join(game_dir, "UserData", "Mods")
                     if not os.path.exists(game_mods_dir): os.makedirs(game_mods_dir)
                     
                     src = os.path.join(self.library_dir, f_name)
                     dst = os.path.join(game_mods_dir, f_name)
                     
                     if os.path.exists(src):
                        if f_name.endswith('.zip'):
                            extract_to = os.path.join(game_mods_dir, os.path.splitext(f_name)[0])
                            if os.path.exists(extract_to):
                                if os.path.isdir(extract_to): shutil.rmtree(extract_to)
                                else: os.remove(extract_to)
                            
                            with zipfile.ZipFile(src, 'r') as z:
                                z.extractall(extract_to)
                        else:
                            shutil.copy2(src, dst)
        return {"status": "success"}

    def load_modpacks(self):
        with open(self.modpacks_file, 'r') as f:
            return json.load(f)

    def get_screenshots(self):
        home = os.path.expanduser('~')
        # Prioritize Hytale specific folders, then generic pictures
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

    def scan_downloads_for_mod(self, mod_id, expected_file_name):
        """Looks for the downloaded mod file in ~/Downloads"""
        home = os.path.expanduser("~")
        downloads = os.path.join(home, "Downloads")
        if not os.path.exists(downloads):
            # Try Portuguese 'Downloads'
            downloads = os.path.join(home, "Transferências")
            if not os.path.exists(downloads):
                return None
        
        # Strip extensions for more flexible matching
        expected_root = expected_file_name.lower().rsplit('.', 1)[0]
        expected_clean = expected_root.replace(" ", "").replace("-", "").replace("_", "")
        
        # Look for files modified in the last 15 minutes
        now = time.time()
        for f in os.listdir(downloads):
            f_lower = f.lower()
            if f_lower.endswith(('.zip', '.jar')):
                # Try simple match first
                if expected_root in f_lower or str(mod_id) in f:
                    path = os.path.join(downloads, f)
                    if now - os.path.getmtime(path) < 900: # 15 minutes
                        return path
                
                # Try cleaner match (ignores spaces/dashes)
                clean_f = f_lower.replace(" ", "").replace("-", "").replace("_", "")
                if expected_clean in clean_f:
                    path = os.path.join(downloads, f)
                    if now - os.path.getmtime(path) < 900:
                        return path
        return None

    def ingest_manual_download(self, mod_id, source_path, expected_file_name):
        """Moves a manually downloaded file to the library and finalizes installation"""
        try:
            if not os.path.exists(source_path):
                return {"status": "error", "message": "Arquivo não encontrado."}
            
            # Destination - Preserve ACTUAL extension detected
            actual_ext = source_path.rsplit('.', 1)[-1].lower()
            final_file_name = expected_file_name.rsplit('.', 1)[0] + "." + actual_ext
            dest_path = os.path.join(self.library_dir, final_file_name)
            
            # Move
            shutil.move(source_path, dest_path)
            
            # Update Library Metadata
            lib = self.load_library()
            meta = self.fetch_mod_metadata(mod_id)
            if meta:
                lib[str(mod_id)] = {
                    "name": meta.get("name", "Unknown"),
                    "logo": meta.get("logo", {}),
                    "summary": meta.get("summary", ""),
                    "file_name": final_file_name
                }
                self.save_library(lib)
            
            # Link to active pack
            active_pack = self.config.get("active_modpack")
            if active_pack:
                self.add_mod_to_pack(active_pack, mod_id)
            
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def delete_mods_from_library(self, mod_ids):
        """Batch delete mods from library and all packs"""
        lib = self.load_library()
        with open(self.modpacks_file, 'r') as f:
            packs = json.load(f)
        
        game_dir = self.config.get("game_dir")
        game_mods_dir = os.path.join(game_dir, "UserData", "Mods") if game_dir else None
        
        count = 0
        for mod_id in mod_ids:
            mod_id_str = str(mod_id)
            info = lib.get(mod_id_str)
            if not info: continue
            
            # Physical file
            file_name = info.get("file_name")
            if file_name:
                lib_path = os.path.join(self.library_dir, file_name)
                if os.path.exists(lib_path): os.remove(lib_path)
                
                # Active game path
                if game_mods_dir:
                    game_path = os.path.join(game_mods_dir, file_name)
                    if os.path.exists(game_path): os.remove(game_path)
            
            # Remove from library
            del lib[mod_id_str]
            
            # Remove from packs
            for pack in packs:
                pack['mods'] = [m for m in pack.get('mods', []) if str(m) != mod_id_str]
            
            count += 1
            
        self.save_library(lib)
        with open(self.modpacks_file, 'w') as f:
            json.dump(packs, f)
            
        return {"status": "success", "count": count}

    def remove_mods_from_pack(self, pack_name, mod_ids):
        """Batch remove mods from a specific pack"""
        with open(self.modpacks_file, 'r') as f:
            packs = json.load(f)
        
        target = next((p for p in packs if p['name'] == pack_name), None)
        if not target: return {"status": "error", "message": "Pack not found"}
        
        is_active = (self.config.get("active_modpack") == pack_name)
        game_dir = self.config.get("game_dir")
        game_mods_dir = os.path.join(game_dir, "UserData", "Mods") if (is_active and game_dir) else None
        
        lib = self.load_library()
        
        count = 0
        mod_ids_set = set(int(m) for m in mod_ids)
        target['mods'] = [m for m in target['mods'] if int(m) not in mod_ids_set]
        
        if game_mods_dir:
            for mod_id in mod_ids:
                info = lib.get(str(mod_id))
                if info and info.get("file_name"):
                    game_path = os.path.join(game_mods_dir, info.get("file_name"))
                    if os.path.exists(game_path): os.remove(game_path)
        
        with open(self.modpacks_file, 'w') as f:
            json.dump(packs, f)
            
        return {"status": "success", "count": len(mod_ids)}
