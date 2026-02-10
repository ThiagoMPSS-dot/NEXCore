import requests
import json
import time
import os
from .constants import CURSEFORGE_API_BASE_URL, GAME_ID
from urllib.request import urlretrieve

class ApiClient:
    def __init__(self, storage_manager):
        self.storage = storage_manager
        self.base_url = CURSEFORGE_API_BASE_URL
        self.game_id = GAME_ID

    def get_api_key(self):
        return self.storage.config.get("api_key", "")

    def get_headers(self):
        return {
            'x-api-key': self.get_api_key(),
            'Accept': 'application/json'
        }

    def _inject_install_status(self, mods_list):
        library = self.storage.load_library()
        installed_ids = set(str(k) for k in library.keys())
        for mod in mods_list:
            mod['isInstalled'] = str(mod['id']) in installed_ids
        return mods_list

    def search_mods(self, query="", sort_field=1, sort_order="desc", offset=0):
        if not self.get_api_key():
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
        if not self.get_api_key(): return "API Key missing"
        try:
            resp = requests.get(f"{self.base_url}/mods/{mod_id}/description", headers=self.get_headers())
            return resp.json().get('data', "") if resp.status_code == 200 else "Descrição indisponível."
        except:
            return "Erro ao carregar descrição."

    def get_recommendations(self, preference=""):
        config = self.storage.config
        if not self.get_api_key(): return {"error": "CurseForge API Key missing"}

        search_term = preference if preference else ""

        # Gemni Integration
        gemini_key = config.get("gemini_api_key")
        if gemini_key and preference:
            try:
                from google import genai
                client = genai.Client(api_key=gemini_key)
                # Note: Assuming google-genai is installed or user has it.
                model_name = config.get("gemini_model", "gemini-1.5-flash")
                prompt = f"Translate this mod preference into a single English keyword or very short phrase (max 2 words) for searching a Minecraft mod database. Return ONLY the keyword, nothing else. Preference: '{preference}'"
                
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                search_term = response.text.strip()
                print(f"[AI Discovery] Gemini translated '{preference}' -> '{search_term}'")
            except Exception as e:
                print(f"[AI Discovery] Gemini Error: {e}")

        # Currently get_recommendations logic in mod_manager was incomplete/placeholder
        # Assuming we just do a search based on preference
        params = {
            'gameId': self.game_id,
            'searchFilter': search_term,
            'sortField': 2, # Popularity
            'sortOrder': 'desc',
            'pageSize': 50 
        }
        # ... logic continues from original (it was partially implemented in snippet) ...
        # For now, replicate search behavior
        return self.search_mods(query=search_term, sort_field=2, sort_order='desc')

    def get_mod_extended_info(self, mod_id):
        if not self.get_api_key(): return {}
        headers = self.get_headers()
        
        try:
            # 1. Get Mod Details
            mod_resp = requests.get(f"{self.base_url}/mods/{mod_id}", headers=headers)
            if mod_resp.status_code != 200: return {}
            mod_data = mod_resp.json().get('data', {})
            
            # Categories
            categories = mod_data.get('categories', [])
            cat_id = categories[0].get('id') if categories else None
            
            # 2. Get Dependencies
            deps_data = []
            latest_files = mod_data.get('latestFiles', [])
            latest_files.sort(key=lambda x: x.get('fileDate', ''), reverse=True)
            
            if latest_files:
                req_deps_ids = []
                for dep in latest_files[0].get('dependencies', []):
                    if dep.get('relationType') == 3: # Required
                        req_deps_ids.append(dep.get('modId'))
                
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
                    'sortField': 2,
                    'sortOrder': 'desc',
                    'pageSize': 6
                }
                sim_resp = requests.get(f"{self.base_url}/mods/search", headers=self.get_headers(), params=params)
                if sim_resp.status_code == 200:
                    candidates = sim_resp.json().get('data', [])
                    for m in candidates:
                        if m['id'] != mod_id:
                            similar_data.append(m)
                            if len(similar_data) >= 5: break
            
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
        if not self.get_api_key(): return None
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
        except: pass
        return None

    def translate_html(self, html_content, target_lang="pt", callback=None):
        if not html_content: return ""
        
        gemini_key = self.storage.config.get("gemini_api_key")
        if gemini_key:
            try:
                from google import genai
                client = genai.Client(api_key=gemini_key)
                model_name = self.storage.config.get("gemini_model", "gemini-1.5-flash")
                
                prompt = (
                    f"Translate the following HTML content to the language '{target_lang}'. "
                    "IMPORTANT: Preserve all HTML tags, attributes, and structure EXACTLY. "
                    "Only translate the user-visible text content. "
                    "Do not add any explanations or markdown code blocks. "
                    f"{html_content}"
                )
                
                response = client.models.generate_content(model=model_name, contents=prompt)
                text = response.text.replace("```html", "").replace("```", "").strip()
                if callback: callback(text)
                return text
            except Exception as e:
                print(f"Gemini Translation Error: {e}")
        
        # Fallback to DeepTranslator
        try:
            from bs4 import BeautifulSoup, NavigableString
            from deep_translator import GoogleTranslator
            
            soup = BeautifulSoup(html_content, 'html.parser')
            translator = GoogleTranslator(source='auto', target=target_lang)
            if target_lang.lower() in ['pt-br', 'pt_br']: target_lang = 'pt'
            
            last_update_time = 0
            for element in soup.descendants:
                if isinstance(element, NavigableString):
                    if element.parent.name in ['script', 'style', 'code', 'pre']: continue
                    txt = str(element).strip()
                    if len(txt) > 2:
                        try:
                            translated = translator.translate(txt, target=target_lang)
                            if translated:
                                element.replace_with(translated)
                                if callback and (time.time() - last_update_time > 0.8):
                                    callback(str(soup))
                                    last_update_time = time.time()
                        except: pass
            
            final_soup = str(soup)
            if callback: callback(final_soup)
            return final_soup
        except Exception as e:
            return f"Erro na tradução: {str(e)}"

    def fetch_mod_metadata(self, mod_id):
        if not self.get_api_key(): return None
        try:
            resp = requests.get(f"{self.base_url}/mods/{mod_id}", headers=self.get_headers())
            if resp.status_code == 200:
                data = resp.json().get('data', {})
                return {
                    "name": data.get("name"),
                    "slug": data.get("slug"),
                    "logo": data.get("logo", {}),
                    "summary": data.get("summary", ""),
                    "links": data.get("links", {})
                }
            return None
        except: return None

    def install_mod_to_library(self, mod_id, mod_metadata=None, processed_ids=None):
        if processed_ids is None: processed_ids = set()
        mod_id_str = str(mod_id)
        if mod_id_str in processed_ids: return {"status": "success", "message": "Já processado"}
        processed_ids.add(mod_id_str)

        if not self.get_api_key(): return {"status": "error", "message": "No API Key"}

        try:
            files_resp = requests.get(
                f"{self.base_url}/mods/{mod_id}/files",
                headers=self.get_headers(),
                params={'pageSize': 1, 'sortOrder': 'desc'}
            )
            files_data = files_resp.json().get('data', [])
            if not files_data: return {"status": "error", "message": "No files found"}
            
            target_file = files_data[0]
            download_url = target_file.get('downloadUrl')
            file_name = target_file.get('fileName') or target_file.get('displayName', f"{mod_id}.zip")

            deps = target_file.get('dependencies', [])
            dep_count = 0
            for dep in deps:
                if dep.get('relationType') == 3:
                     self.install_mod_to_library(dep.get('modId'), processed_ids=processed_ids)
                     dep_count += 1

            dest_path = os.path.join(self.storage.library_dir, file_name)
            if not os.path.exists(dest_path):
                if not download_url:
                     slug = ""
                     if mod_metadata: slug = mod_metadata.get('slug', "")
                     else:
                        meta = self.fetch_mod_metadata(mod_id)
                        if meta: slug = meta.get('slug', "")
                     
                     file_id = target_file.get('id')
                     manual_url = f"https://www.curseforge.com/hytale/mods/{slug}/download/{file_id}" if slug else "https://www.curseforge.com/hytale/mods"
                     return {
                         "status": "manual_required", 
                         "message": "Download manual necessário.",
                         "url": manual_url,
                         "file_name": file_name,
                         "mod_id": mod_id
                     }

                urlretrieve(download_url, dest_path)

            if not mod_metadata:
                mod_metadata = self.fetch_mod_metadata(mod_id)
            
            if mod_metadata:
                lib = self.storage.load_library()
                internal_id = self.storage._extract_internal_id(dest_path)
                lib[mod_id_str] = {
                    "name": mod_metadata.get("name", "Unknown"),
                    "internal_id": internal_id or "Unknown:Unknown",
                    "logo": mod_metadata.get("logo", {}),
                    "summary": mod_metadata.get("summary", ""),
                    "file_name": file_name
                }
                self.storage.save_library(lib)

            # Auto-link to active pack moved to orchestration level ideally, requestor handles it.
            # But here we can access storage config.
            active_pack = self.storage.config.get("active_modpack")
            linked_msg = ""
            if active_pack:
                 # Need 'add_mod_to_pack' logic. Ideally API shouldn't modify pack structure directly?
                 # 'install_mod' implies installation. We should replicate 'add_mod_to_pack' logic here OR call back.
                 # For now, let's implement the logic using storage directly.
                 # Reusing storage method? Storage doesn't have 'add_mod_to_pack'.
                 # We will add a simple helper in storage or just do it here.
                 pass 
                 # Wait, 'add_mod_to_pack' is in ModManager.
                 # Let's return success and let ModManager wrapper handle linking?
                 # Ah, the original code did it inside install.
                 # Let's leave linking to the orchestrator to keep API Client pure?
                 # Yes.

            msg = f"Instalado com {dep_count} dependências" if dep_count > 0 else "Instalado"
            return {"status": "success", "file_name": file_name, "message": msg}

        except Exception as e:
            return {"status": "error", "message": str(e)}
