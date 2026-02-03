import webview
import os
from urllib.parse import unquote
import sys
import threading
import socket
import webbrowser
import json
from http.server import HTTPServer, SimpleHTTPRequestHandler
import tkinter as tk
from tkinter import filedialog
from mod_manager import ModManager

CURRENT_VERSION = "1.0.0"
REPO_URL = "https://api.github.com/repos/ThiagoMPSS-dot/NEXCore/releases/latest"

class Api:
    def __init__(self):
        self.manager = ModManager()
        self.window = None

    def set_window(self, window):
        self.window = window

    def search_mods_py(self, query, sort_field=2, offset=0):
        return self.manager.search_mods(query, sort_field=sort_field, offset=offset)

    def get_mod_description_py(self, mod_id):
        return self.manager.get_mod_description(mod_id)

    def get_mod_extended_info_py(self, mod_id):
        return self.manager.get_mod_extended_info(mod_id)

    def get_recommendations_py(self, preference=""):
        return self.manager.get_recommendations(preference)

    def get_mod_by_slug_py(self, slug):
        return self.manager.search_by_slug(slug)

    def translate_description_html_py(self, html, target_lang="pt"):
        def on_update(partial):
            if self.window:
                safe_html = json.dumps(partial)
                self.window.evaluate_js(f"const el = document.getElementById('detail-description'); if(el) el.innerHTML = {safe_html}")
        
        return self.manager.translate_html(html, target_lang, callback=on_update)

    def open_external_link_py(self, url):
        webbrowser.open(url)

    def install_mod_py(self, mod_id, metadata=None):
        return self.manager.install_mod_to_library(mod_id, metadata)

    def save_modpack_py(self, name, mod_ids):
        return self.manager.save_modpack(name, mod_ids)

    def load_modpacks_py(self, params=None): 
        return self.manager.load_modpacks()

    def get_modpack_details_py(self, name):
        return self.manager.get_modpack_details(name)

    def remove_mod_from_pack_py(self, pack, mod_id):
        return self.manager.remove_mod_from_pack(pack, mod_id)
        
    def add_mod_to_pack_py(self, pack, mod_id):
        return self.manager.add_mod_to_pack(pack, mod_id)

    def activate_modpack_py(self, name):
        return self.manager.activate_modpack(name)

    def launch_game_py(self):
        def run_launch():
            def status_callback(status):
                if self.window:
                    self.window.evaluate_js(f"if(window.updatePlayButtonState) window.updatePlayButtonState('{status}')")
            
            def console_callback(line):
                if self.window:
                    # Escape line for JS
                    safe_line = json.dumps(line)
                    self.window.evaluate_js(f"if(window.appendConsoleLine) window.appendConsoleLine({safe_line})")

            res = self.manager.launch_game(status_callback=status_callback, console_callback=console_callback)
            
            if res.get('status') == 'error':
                if self.window:
                    msg = json.dumps(res.get('message', 'Erro desconhecido ao iniciar'))
                    # Show alert and reset button
                    self.window.evaluate_js(f"alertApp({msg}); if(window.updatePlayButtonState) window.updatePlayButtonState('finished');")

        thread = threading.Thread(target=run_launch)
        thread.start()
        
        return {"status": "started"}

    def delete_modpack_py(self, name):
        return self.manager.delete_modpack(name)

    def get_library_py(self):
        return self.manager.load_library()

    def delete_mod_from_library_py(self, mod_id):
        return self.manager.delete_mod_from_library(mod_id)

    def delete_mods_from_library_py(self, mod_ids):
        return self.manager.delete_mods_from_library(mod_ids)

    def remove_mods_from_pack_py(self, pack, mod_ids):
        return self.manager.remove_mods_from_pack(pack, mod_ids)

    def fetch_mod_metadata_py(self, mod_id):
        return self.manager.fetch_mod_metadata(mod_id)

    def save_config_py(self, cfg):
        return self.manager.save_config(cfg)

    def scan_downloads_for_mod_py(self, mod_id, expected_file_name):
        return self.manager.scan_downloads_for_mod(mod_id, expected_file_name)

    def ingest_manual_download_py(self, mod_id, source_path, expected_file_name):
        return self.manager.ingest_manual_download(mod_id, source_path, expected_file_name)

    def get_screenshots_py(self):
        return self.manager.get_screenshots()

    def get_config_py(self, params=None):
        return self.manager.config

    def get_saves_for_pack_py(self, pack_name):
        return self.manager.get_saves_for_pack(pack_name)

    def create_save_py(self, pack_name, config):
        return self.manager.create_save(pack_name, config)

    def get_pack_logs_py(self, pack_name):
        return self.manager.get_pack_logs(pack_name)

    def read_log_file_py(self, pack_name, save_name, file_name):
        return self.manager.read_log_file(pack_name, save_name, file_name)

    def update_save_py(self, pack_name, folder_name, config):
        return self.manager.update_save(pack_name, folder_name, config)

    def delete_save_py(self, pack_name, folder_name):
        return self.manager.delete_save(pack_name, folder_name)

    def export_modpack_cf_py(self, pack_name):
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        
        target_path = filedialog.asksaveasfilename(
            title=f"Exportar Modpack: {pack_name}",
            defaultextension=".zip",
            initialfile=f"{pack_name}_CurseForge.zip",
            filetypes=[("ZIP files", "*.zip")]
        )
        root.destroy()
        
        if not target_path:
            return {"status": "cancelled"}
            
        def progress(msg):
            if self.window:
                self.window.evaluate_js(f"if(window.updateProgress) window.updateProgress({json.dumps(msg)})")
        
        return self.manager.export_modpack_cf(pack_name, target_path, progress_callback=progress)

    def import_modpack_cf_py(self):
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        
        file_path = filedialog.askopenfilename(
            title="Selecionar Modpack CurseForge (ZIP)",
            filetypes=[("ZIP files", "*.zip")]
        )
        root.destroy()
        
        if file_path:
            def progress(msg):
                if self.window:
                    self.window.evaluate_js(f"if(window.updateProgress) window.updateProgress({json.dumps(msg)})")
            
            return self.manager.import_modpack_cf(file_path, progress_callback=progress)
        return {"status": "cancelled"}

    def check_for_updates_py(self):
        """Checks for new releases on GitHub"""
        try:
            import requests
            response = requests.get(REPO_URL, timeout=5)
            if response.status_code == 200:
                data = response.json()
                latest_version = data.get("tag_name", "v1.0.0").replace("v", "")
                current = CURRENT_VERSION.replace("v", "")
                
                # Simple version comparison
                if latest_version > current:
                    return {
                        "status": "update_available",
                        "version": latest_version,
                        "url": data.get("html_url"),
                        "body": data.get("body", "")
                    }
            return {"status": "up_to_date"}
        except:
            return {"status": "up_to_date"} # Fail silently to not bug the user

    def generate_map_py(self, pack_name, save_name):
        res = self.manager.generate_world_map(pack_name, save_name)
        if res['status'] == 'success':
            # Convert absolute path to local server URL
            # The server serves root_dir which is CWD.
            # image_path is absolute. 
            # We need to serve it via the /save-preview/ handler or just make it relative if in web root (it's not).
            # Wait, the HTTP server in main.py has a special handler for /save-preview/!
            # See line 158 of main.py in previous view: do_GET handle /save-preview/
            # It expects /save-preview/PackName/FolderName/file?
            # Actually the generate_world_map returns absolute path.
            # The custom handler logic:
            # if self.path.startswith('/save-preview/'): ...
            # parts = [_, save-preview, PackName, FolderName]
            # So we just need to return a URL that matches this pattern.
            # The file generated is 'map_preview.png'.
            # So URL: /save-preview/{pack_name}/{save_name}/map_preview.png
            return {"status": "success", "url": f"/save-preview/{pack_name}/{save_name}/map_preview.png"}
        return res

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def get_screenshots_dir():
    home = os.path.expanduser('~')
    # Prioritize Hytale specific folders, then generic pictures
    candidates = [
        os.path.join(home, 'Pictures', 'Hytale Screenshots'),
        os.path.join(home, 'Imagens', 'Hytale Screenshots'),
        os.path.join(home, 'Pictures'),
        os.path.join(home, 'Imagens')
    ]
    for p in candidates:
        if os.path.exists(p): return p
    return os.path.join(home, 'Pictures') # Fallback

def start_server(port, root_dir):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=root_dir, **kwargs)
        
        # Suppress logging to keep console clean
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            if self.path.startswith('/save-preview/'):
                # Format: /save-preview/PackName/FolderName
                parts = self.path.split('/')
                if len(parts) >= 4:
                    pack_name = unquote(parts[2])
                    folder_name = unquote(parts[3])
                    
                    # Security: No parent directory traversal
                    pack_name = os.path.basename(pack_name)
                    folder_name = os.path.basename(folder_name)
                    
                    filename = "preview.png"
                    if len(parts) >= 5:
                        raw_filename = os.path.basename(unquote(parts[4]))
                        # Strip query parameters (e.g. ?t=123)
                        filename = raw_filename.split('?')[0]
                    
                    file_path = os.path.join(os.getcwd(), "data", "packs", pack_name, "saves", folder_name, filename)
                    
                    if os.path.exists(file_path):
                        self.send_response(200)
                        self.send_header('Content-type', 'image/png')
                        self.end_headers()
                        with open(file_path, 'rb') as f:
                            self.wfile.write(f.read())
                    else:
                        self.send_error(404, "Preview not found")
                else:
                    self.send_error(400, "Invalid path")
                return

            if self.path.startswith('/screenshots/'):
                # Extract filename
                filename = self.path.replace('/screenshots/', '')
                # Security check
                safe_name = os.path.basename(filename)
                
                target_dir = get_screenshots_dir()
                file_path = os.path.join(target_dir, safe_name)
                
                if os.path.exists(file_path):
                    self.send_response(200)
                    self.send_header('Content-type', 'image/png')
                    self.end_headers()
                    with open(file_path, 'rb') as f:
                        self.wfile.write(f.read())
                else:
                    self.send_error(404, "File not found")
                return
            
            super().do_GET()

    httpd = HTTPServer(('127.0.0.1', port), Handler)
    httpd.serve_forever()

def start_app():
    api = Api()
    
    # Setup Paths
    base_dir = os.path.dirname(os.path.abspath(__file__))
    web_dir = os.path.join(base_dir, 'web')
    
    # Start Server
    port = find_free_port()
    t = threading.Thread(target=start_server, args=(port, web_dir))
    t.daemon = True
    t.start()
    
    url = f'http://127.0.0.1:{port}/index.html'
    icon_path = os.path.join(web_dir, 'assets', 'icon.png')

    window = webview.create_window(
        'NEXCore', 
        url, 
        js_api=api,
        width=1200, 
        height=800,
        resizable=True,
        text_select=False
    )
    api.set_window(window)
    
    print(f"Starting NEXCore on {url}")
    
    # Cross-platform GUI selection
    # Reverting to auto-detect because forced GTK caused Segmention Fault (139) on some setups.
    # We still keep the CRITICAL log level to hide the SIP enum noise.
    gui_backend = None 
    
    # Silence pywebview logger noise
    import logging
    logging.getLogger('pywebview').setLevel(logging.CRITICAL)
    
    webview.start(debug=False, icon=icon_path, gui=gui_backend)

if __name__ == '__main__':
    start_app()
