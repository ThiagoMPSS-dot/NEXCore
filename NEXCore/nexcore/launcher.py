import os
import shutil
import subprocess
import threading
import time
import zipfile
import sys
import psutil

class Launcher:
    def __init__(self, storage_manager, api_client):
        self.storage = storage_manager
        self.api_client = api_client
        self.is_launching = False
        self.sync_lock = threading.Lock()

    def _get_saves_dir(self, game_dir):
        p_upper = os.path.join(game_dir, "UserData", "Saves")
        p_lower = os.path.join(game_dir, "UserData", "saves")
        if os.path.exists(p_lower) and not os.path.exists(p_upper):
            try: os.rename(p_lower, p_upper)
            except: pass
        if os.path.exists(p_lower) and os.path.exists(p_upper):
            try: 
                if not os.listdir(p_lower): os.rmdir(p_lower)
            except: pass
        return p_upper

    def _clear_directory(self, path):
         self.storage.clear_directory(path)

    def _copytree_with_filter(self, src, dst, ignore_folders=True):
        if not os.path.exists(dst): os.makedirs(dst)
        for item in os.listdir(src):
            s = os.path.join(src, item)
            d = os.path.join(dst, item)
            if os.path.isdir(s):
                if ignore_folders and item in ['Backup', 'backup', 'logs', 'map_cache']: continue
                shutil.copytree(s, d)
            else:
                shutil.copy2(s, d)

    def _backup_current_game_state(self, mods_dir, saves_dir, callback=None):
        if callback: callback("Criando backup de segurança dos seus arquivos...")
        self._clear_directory(self.storage.temp_backups_dir)
        try:
            if os.path.exists(mods_dir) and os.listdir(mods_dir):
                dst = os.path.join(self.storage.temp_backups_dir, "Mods")
                self._copytree_with_filter(mods_dir, dst, ignore_folders=True)
            if os.path.exists(saves_dir) and os.listdir(saves_dir):
                dst = os.path.join(self.storage.temp_backups_dir, "Saves")
                self._copytree_with_filter(saves_dir, dst, ignore_folders=True)
        except Exception as e:
            print(f"Erro backup: {e}")

    def _restore_original_game_state(self, mods_dir, saves_dir, callback=None):
        if callback: callback("Restaurando seus arquivos originais...")
        try:
            src_mods = os.path.join(self.storage.temp_backups_dir, "Mods")
            if os.path.exists(src_mods):
                if not os.path.exists(mods_dir): os.makedirs(mods_dir)
                for item in os.listdir(src_mods):
                    s = os.path.join(src_mods, item)
                    d = os.path.join(mods_dir, item)
                    if os.path.isdir(s): shutil.copytree(s, d)
                    else: shutil.copy2(s, d)

            src_saves = os.path.join(self.storage.temp_backups_dir, "Saves")
            if os.path.exists(src_saves):
                if not os.path.exists(saves_dir): os.makedirs(saves_dir)
                for item in os.listdir(src_saves):
                    s = os.path.join(src_saves, item)
                    d = os.path.join(saves_dir, item)
                    if os.path.isdir(s): shutil.copytree(s, d)
                    else: shutil.copy2(s, d)
            
            self._sync_cache_folders_from_game(mods_dir, saves_dir)
            self._clear_directory(self.storage.temp_backups_dir)
        except Exception as e:
            print(f"Erro restore: {e}")

    def _sync_cache_folders_from_game(self, game_mods_dir, game_saves_dir):
        try:
            if not os.path.exists(game_saves_dir): return
            for save_name in os.listdir(game_saves_dir):
                game_save_path = os.path.join(game_saves_dir, save_name)
                if not os.path.isdir(game_save_path): continue
                
                # Find matching save in NEXCore
                for pack_name in os.listdir(self.storage.packs_dir):
                    pack_saves_dir = os.path.join(self.storage.packs_dir, pack_name, "saves")
                    nexcore_save_path = os.path.join(pack_saves_dir, save_name)
                    if os.path.exists(nexcore_save_path):
                        for folder in ['Backup', 'logs', 'map_cache']:
                            game_folder = os.path.join(game_save_path, folder)
                            nexcore_folder = os.path.join(nexcore_save_path, folder)
                            if os.path.exists(game_folder):
                                if os.path.exists(nexcore_folder): shutil.rmtree(nexcore_folder)
                                shutil.copytree(game_folder, nexcore_folder)
        except: pass

    def sync_modpack_to_game(self, callback=None):
        game_dir = self.storage.config.get("game_dir")
        pack_name = self.storage.config.get("active_modpack")
        
        if not game_dir or not os.path.exists(game_dir):
            return {"status": "error", "message": "Diretório do jogo inválido."}
        if not pack_name:
            return {"status": "success", "info": "Nenhum modpack ativo."}

        game_mods_dir = os.path.join(game_dir, "UserData", "Mods")
        game_saves_dir = self._get_saves_dir(game_dir)

        self._backup_current_game_state(game_mods_dir, game_saves_dir, callback=callback)

        if callback: callback("Limpando pasta de mods...")
        if not os.path.exists(game_mods_dir): os.makedirs(game_mods_dir)
        self._clear_directory(game_mods_dir)

        packs = self.storage.load_modpacks()
        target_pack = next((p for p in packs if p['name'] == pack_name), None)
        if not target_pack: return {"status": "error", "message": "Pack config gone"}

        errors = []
        mods_list = target_pack.get('mods', [])
        total_mods = len(mods_list)
        
        for i, mod_id in enumerate(mods_list):
            if callback: callback(f"Sincronizando mod {i+1}/{total_mods}...")
            
            # Use API Client to ensure mod is in library
            res = self.api_client.install_mod_to_library(mod_id)
            if res['status'] == 'success' or res['status'] == 'manual_required':
                 f_name = res.get('file_name')
                 if not f_name: continue
                 
                 src = os.path.join(self.storage.library_dir, f_name)
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

        if self.storage.config.get("manage_saves"):
            if callback: callback("Sincronizando Saves...")
            if not os.path.exists(game_saves_dir): os.makedirs(game_saves_dir)
            self._clear_directory(game_saves_dir)
            
            target_saves = os.path.join(self.storage.packs_dir, pack_name, "saves")
            if os.path.exists(target_saves):
                for item in os.listdir(target_saves):
                    if item.lower() in ('logs', 'backups', 'backup'): continue
                    s = os.path.join(target_saves, item)
                    d = os.path.join(game_saves_dir, item)
                    if os.path.isdir(s):
                        self._copytree_with_filter(s, d, ignore_folders=True)
                    else:
                        shutil.copy2(s, d)
        
        return {"status": "success", "errors": errors}

    def cleanup_after_game(self, pack_name, callback=None):
        if not pack_name: return
        with self.sync_lock:
            game_dir = self.storage.config.get("game_dir")
            if not game_dir or not os.path.exists(game_dir): return

            game_mods_dir = os.path.join(game_dir, "UserData", "Mods")
            game_saves_dir = self._get_saves_dir(game_dir)

            if self.storage.config.get("manage_saves") and os.path.exists(game_saves_dir):
                if callback: callback("Sincronizando mundos (NEXCore -> Cache)...")
                pack_dir = os.path.join(self.storage.packs_dir, pack_name)
                pack_saves_dir = os.path.join(pack_dir, "saves")
                try:
                    if not os.path.exists(pack_dir): os.makedirs(pack_dir)
                    if os.path.exists(pack_saves_dir): shutil.rmtree(pack_saves_dir)
                    shutil.copytree(game_saves_dir, pack_saves_dir)
                except Exception as e: print(f"Error syncing back: {e}")

            if callback: callback("Limpando arquivos temporários...")
            self._clear_directory(game_mods_dir)
            if self.storage.config.get("manage_saves"):
                self._clear_directory(game_saves_dir)

            self._restore_original_game_state(game_mods_dir, game_saves_dir, callback=callback)

    def launch_game(self, status_callback=None, console_callback=None):
        if self.is_launching: return {"status": "error", "message": "Já iniciando"}
        self.is_launching = True
        
        try:
            active_pack = self.storage.config.get("active_modpack")
            if status_callback: status_callback("Sincronizando...")
            sync_res = self.sync_modpack_to_game(callback=status_callback)
            if sync_res.get('status') == 'error':
                self.is_launching = False
                return sync_res

            game_path = self.storage.config.get("game_dir")
            if not game_path: 
                game_path = self.storage.try_auto_detect_game()
                if not game_path:
                    self.is_launching = False
                    return {"status": "error", "message": "Configure o diretório do jogo."}
            
            game_path = os.path.expanduser(game_path)
            target_exe = None
            if os.path.isdir(game_path):
                candidates = ["hytale-launcher", "HytaleLauncher.exe", "hytale-launcher.exe"]
                if sys.platform == 'win32': candidates = ["HytaleLauncher.exe", "hytale-launcher.exe"]
                
                for c in candidates:
                    full_p = os.path.join(game_path, c)
                    if os.path.exists(full_p) and not os.path.isdir(full_p):
                        target_exe = full_p
                        break
                if not target_exe:
                    # Generic open logic
                    self.is_launching = False
                    if sys.platform.startswith('linux'): subprocess.Popen(['xdg-open', game_path])
                    elif sys.platform == 'win32': os.startfile(game_path)
                    return {"status": "success", "info": "Pasta aberta (exe não encontrado)"}
            else:
                target_exe = game_path

            is_flatpak = sys.platform.startswith('linux') and '.var/app/com.hypixel.HytaleLauncher' in target_exe
            cmd = ["flatpak", "run", "com.hypixel.HytaleLauncher"] if is_flatpak else [target_exe]
            
            if not is_flatpak and sys.platform != 'win32':
                 st = os.stat(target_exe)
                 os.chmod(target_exe, st.st_mode | 0o111)

            if status_callback: status_callback("Iniciando Jogo...")
            proc = subprocess.Popen(
                cmd, 
                cwd=os.path.dirname(target_exe) if not is_flatpak else None, 
                env=os.environ.copy(),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
            )

            def monitor():
                try:
                    if console_callback:
                        for line in iter(proc.stdout.readline, ""):
                            console_callback(line.strip())
                    proc.wait()
                    
                    # Polling logic for client
                    game_found = False
                    start_time = time.time()
                    while time.time() - start_time < 30:
                        for p in psutil.process_iter(['name']):
                            try:
                                if p.info['name'] == 'HytaleClient':
                                    game_found = True
                                    if status_callback: status_callback("playing")
                                    p.wait()
                                    break
                            except: continue
                        if game_found: break
                        time.sleep(1)
                    
                    if active_pack:
                        self.cleanup_after_game(active_pack, callback=status_callback)
                    
                    self.is_launching = False
                    if status_callback: status_callback("finished")
                except Exception as e:
                    print(f"Monitor error: {e}")
                    self.is_launching = False

            threading.Thread(target=monitor, daemon=True).start()
            return {"status": "success", "message": "Iniciando..."}

        except Exception as e:
            self.is_launching = False
            return {"status": "error", "message": str(e)}
