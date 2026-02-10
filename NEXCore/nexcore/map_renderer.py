
import os
import json
import logging
import struct
import io
import zstandard as zstd
import hashlib
from PIL import Image

logger = logging.getLogger("MapGen")

class MapRenderer:
    # Cores padrão para blocos comuns do Hytale (Fallback)
    DEFAULT_PALETTE = {
        "air": (0, 0, 0),
        "stone": (120, 120, 120),
        "soil_dirt": (134, 96, 67),
        "grass": (91, 142, 49),
        "grass_top": (91, 142, 49),
        "soil_grass": (91, 142, 49),
        "soil_grass_sunny": (100, 160, 50),
        "water": (63, 118, 228),
        "sand": (219, 211, 160),
        "gravel": (149, 145, 141),
        "wood_oak_log": (103, 82, 49),
        "wood_oak_leaves": (58, 95, 37),
        "wood_birch_log": (217, 216, 203),
        "wood_birch_leaves": (109, 138, 91),
        "wood_spruce_log": (56, 39, 23),
        "wood_spruce_leaves": (56, 77, 52),
        "snow": (240, 240, 240),
        "ice": (165, 198, 239)
    }

    def __init__(self, storage):
        self.storage = storage
        self.block_palette = self.DEFAULT_PALETTE.copy()
        self._init_map_engine()
        
        # Configure logging to map_gen.log
        log_handler = logging.FileHandler('map_gen.log', mode='a')
        log_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        logger.addHandler(log_handler)
        logger.setLevel(logging.INFO)

    def _init_map_engine(self):
        palette_path = os.path.join(self.storage.data_dir, "block_colors.json")
        if os.path.exists(palette_path):
            try:
                with open(palette_path, 'r') as f:
                    raw_palette = json.load(f)
                    # Mesclar/Sobrescrever defaults com o que vier do JSON
                    for k, v in raw_palette.items():
                        self.block_palette[k.lower()] = tuple(v)
            except Exception as e:
                logger.error(f"Error loading block_colors.json: {e}")

    def _get_id_color(self, gid):
        h = hashlib.md5(str(gid).encode()).digest()
        r, g, b = 50 + (h[0] % 150), 50 + (h[1] % 150), 50 + (h[2] % 150)
        return (r, g, b)

    def _unpack_12bit(self, data):
        blocks = [0] * 16384
        for i in range(8192):
            off = i * 3
            if off + 2 < len(data):
                b1, b2, b3 = data[off], data[off+1], data[off+2]
                blocks[i*2] = b1 | ((b2 & 0x0F) << 8)
                blocks[i*2+1] = (b2 >> 4) | (b3 << 4)
        return blocks

    def _unpack_6bit(self, data):
        blocks = [0] * 16384
        for i in range(16384 // 4):
            off = (i * 3)
            if off + 2 < len(data):
                b = data[off:off+3]
                blocks[i*4] = b[0] & 0x3F
                blocks[i*4+1] = ((b[0] >> 6) | (b[1] << 2)) & 0x3F
                blocks[i*4+2] = ((b[1] >> 4) | (b[2] << 4)) & 0x3F
                blocks[i*4+3] = (b[2] >> 2) & 0x3F
        return blocks

    def _fast_extract_sections(self, decomp):
        sections_found = []
        s_idx = decomp.find(b'Sections\x00')
        if s_idx == -1: return []
        size_idx = s_idx + 9
        if size_idx + 4 > len(decomp): return []
        list_size = struct.unpack('<I', decomp[size_idx:size_idx+4])[0]
        list_payload = decomp[size_idx+4 : size_idx+4+list_size]
        b_cursor = 0
        while True:
            b_idx = list_payload.find(b'Block\x00', b_cursor)
            if b_idx == -1: break
            bs_idx = b_idx + 6
            if bs_idx + 4 > len(list_payload): break
            b_size = struct.unpack('<I', list_payload[bs_idx:bs_idx+4])[0]
            b_pld = list_payload[bs_idx+4 : bs_idx+4+b_size]
            pal, data = [], None
            pidx = b_pld.find(b'Palette\x00')
            didx = b_pld.find(b'Data\x00')
            if pidx != -1:
                psize = struct.unpack('<I', b_pld[pidx+8:pidx+12])[0]
                ppld = b_pld[pidx+12:pidx+12+psize]
                for i in range(len(ppld)-5):
                    if ppld[i] == 0x07: # Int TID
                        null_at = ppld.find(b'\x00', i+1)
                        if null_at != -1 and null_at+4 < len(ppld):
                            pal.append(struct.unpack('<i', ppld[null_at+1:null_at+5])[0])
                if not pal:
                    for i in range(0, (len(ppld)//4)*4, 4): pal.append(struct.unpack('<I', ppld[i:i+4])[0])
            if didx != -1:
                dsize = struct.unpack('<I', b_pld[didx+5:didx+9])[0]
                data = b_pld[didx+9:didx+9+dsize]
            if data: sections_found.append({"Palette": pal, "Data": data})
            b_cursor = b_idx + 10 + b_size
        return sections_found

    def _render_chunk_brute(self, decompressed, pixels, world_palette, local_palette, chunk_lx, chunk_lz, metadata_palette=None):
        base_x, base_z = chunk_lx * 32, chunk_lz * 32
        sections = self._fast_extract_sections(decompressed)
        if not sections: return False
        rendered = False
        
        # Processar seções de BAIXO para CIMA (não reversed)
        # Isso garante que blocos mais altos sobrescrevam os mais baixos
        for section in sections:
            try:
                data_blob, l2g = section["Data"], section["Palette"]
                if len(data_blob) >= 24576: packed = self._unpack_12bit(data_blob)
                elif len(data_blob) == 16384: packed = list(data_blob)
                else: packed = self._unpack_6bit(data_blob)
                
                # Para cada posição XZ nesta seção
                for lz in range(32):
                    for lx in range(32):
                        px, pz = base_x + lx, base_z + lz
                        if px >= 1024 or pz >= 1024: continue
                        
                        # Procurar o bloco mais alto (de cima para baixo) nesta seção
                        for ly in range(15, -1, -1):
                            b_idx = lx + (lz * 32) + (ly * 1024)
                            if b_idx >= len(packed) or packed[b_idx] == 0: continue
                            lid = packed[b_idx]
                            gid = l2g[lid] if lid < len(l2g) else lid
                            
                            # Tentar resolver o nome do bloco
                            bname = None
                            if world_palette:
                                bname = world_palette.get(str(gid))
                            if not bname and metadata_palette and gid < len(metadata_palette):
                                bname = metadata_palette[gid]
                            
                            # Se não temos nome, usar o GID diretamente para gerar cor
                            if not bname:
                                color = self._get_id_color(gid)
                                pixels[px, pz] = color
                                if f"block_{gid}" not in local_palette: local_palette.append(f"block_{gid}")
                                rendered = True
                                break
                            
                            # Se temos nome mas é ar, pular
                            if bname.lower() == "air": continue
                            
                            # Renderizar com a cor do nome ou gerar cor baseada no GID
                            pixels[px, pz] = self.block_palette.get(bname.lower(), self._get_id_color(gid))
                            if bname not in local_palette: local_palette.append(bname)
                            rendered = True
                            break
            except: continue
        
        return rendered

    def render_region_tile(self, pack_name, save_name, rx, rz, world_name=None, force=False):
        save_path = os.path.join(self.storage.packs_dir, pack_name, "saves", save_name)
        worlds_dir = os.path.join(save_path, "universe", "worlds")
        target_world, world_name = None, world_name
        if os.path.exists(worlds_dir):
            worlds = os.listdir(worlds_dir)
            if not target_world:
                for w in ["zone3_taiga1_world", "default_world", "default"]:
                    if w in worlds: target_world, world_name = os.path.join(worlds_dir, w), w; break
            if not target_world and worlds: target_world, world_name = os.path.join(worlds_dir, worlds[0]), worlds[0]
            elif world_name and world_name in worlds: target_world = os.path.join(worlds_dir, world_name)
        if not target_world: return {"status": "error", "message": "World not found"}
        region_file = os.path.join(target_world, "chunks", f"{rx}.{rz}.region.bin")
        if not os.path.exists(region_file): return {"status": "error", "message": "Region file not found"}

        world_palette, meta_palette = {}, None
        palette_lookups = [os.path.join(target_world, "static_data", "block_palette.json"), os.path.join(save_path, "block_palette.json")]
        for p_path in palette_lookups:
            if os.path.exists(p_path):
                try:
                    with open(p_path, 'r') as f: world_palette = json.load(f); break
                except: pass
        m_path = os.path.join(save_path, "map_metadata.json")
        if os.path.exists(m_path):
            try:
                with open(m_path, 'r') as f: meta_palette = json.load(f).get("palette")
            except: pass

        img = Image.new('RGB', (1024, 1024), color=(20, 20, 25))
        pxs, l_pal, rendered_count = img.load(), ["Air"], 0
        try:
            with open(region_file, "rb") as f:
                f.seek(40); offsets = struct.unpack(f'>1024I', f.read(4096)); dctx = zstd.ZstdDecompressor()
                for o_idx, b_idx in enumerate(offsets):
                    if b_idx == 0: continue
                    try:
                        f.seek(b_idx * 4096 + 40); decomp = dctx.decompress(f.read(1024*256), max_output_size=1048576)
                        if self._render_chunk_brute(decomp, pxs, world_palette, l_pal, o_idx%32, o_idx//32, meta_palette): rendered_count += 1
                    except: continue
        except Exception as e: logger.error(f"Region error: {e}")

        c_dir = os.path.join(save_path, "map_cache"); os.makedirs(c_dir, exist_ok=True)
        img.save(os.path.join(c_dir, f"{rx}.{rz}.png"))
        with open(os.path.join(c_dir, f"{rx}.{rz}.json"), "w") as f:
            json.dump({"rx": rx, "rz": rz, "world": world_name, "chunks": rendered_count, "palette": list(set(l_pal))}, f)
        return {"status": "success", "tile_url": f"/save-tile/{pack_name}/{save_name}/{rx}.{rz}.png"}

    def generate_world_map(self, pack_name, save_name, world_name=None, force=False):
        """Gera o mapa completo de um mundo, renderizando todas as regiões disponíveis."""
        logger.info(f"Iniciando geração de mapa para {pack_name}/{save_name} (Mundo: {world_name or 'auto'})")
        
        save_path = os.path.join(self.storage.packs_dir, pack_name, "saves", save_name)
        worlds_dir = os.path.join(save_path, "universe", "worlds")
        
        # Descobrir o mundo alvo
        target_world, world_name = None, world_name
        if os.path.exists(worlds_dir):
            worlds = os.listdir(worlds_dir)
            if world_name and world_name in worlds:
                target_world = os.path.join(worlds_dir, world_name)
            elif not target_world:
                for w in ["zone3_taiga1_world", "default_world", "default"]:
                    if w in worlds: 
                        target_world, world_name = os.path.join(worlds_dir, w), w
                        break
            if not target_world and worlds: 
                target_world, world_name = os.path.join(worlds_dir, worlds[0]), worlds[0]
        
        if not target_world or not os.path.exists(target_world):
            logger.error("Mundo não encontrado para geração de mapa")
            return {"status": "error", "message": "World not found"}
        
        chunks_dir = os.path.join(target_world, "chunks")
        if not os.path.exists(chunks_dir):
            logger.error(f"Diretório de chunks não encontrado: {chunks_dir}")
            return {"status": "error", "message": "Chunks directory not found"}
        
        # Escanear todas as regiões disponíveis
        region_files = [f for f in os.listdir(chunks_dir) if f.endswith('.region.bin')]
        logger.info(f"Encontradas {len(region_files)} regiões para renderizar")
        
        rendered_regions = []
        failed_regions = []
        
        for region_file in region_files:
            try:
                # Extrair coordenadas do nome do arquivo (ex: -1.-1.region.bin)
                coords = region_file.replace('.region.bin', '').split('.')
                rx, rz = int(coords[0]), int(coords[1])
                
                logger.info(f"Renderizando região {rx}.{rz}...")
                result = self.render_region_tile(pack_name, save_name, rx, rz, world_name, force)
                
                if result.get("status") == "success":
                    rendered_regions.append({"x": rx, "z": rz})
                    logger.info(f"Região {rx}.{rz} renderizada com sucesso")
                else:
                    failed_regions.append({"x": rx, "z": rz, "error": result.get("message", "Unknown error")})
                    logger.warning(f"Falha ao renderizar região {rx}.{rz}: {result.get('message')}")
            except Exception as e:
                logger.error(f"Erro ao processar região {region_file}: {e}")
                failed_regions.append({"file": region_file, "error": str(e)})
        
        logger.info(f"Geração de mapa concluída. Renderizadas: {len(rendered_regions)}, Falhas: {len(failed_regions)}")
        
        # Criar preview consolidado (imagem de baixa resolução de todas as regiões)
        preview_path = os.path.join(save_path, "map_preview.png")
        metadata_path = os.path.join(save_path, "map_metadata.json")
        
        # Salvar metadados
        metadata = {
            "world": world_name,
            "regions_rendered": len(rendered_regions),
            "regions_failed": len(failed_regions),
            "palette": ["Air", "stone", "soil_dirt"]  # Paleta básica, pode ser expandida
        }
        
        try:
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            logger.info(f"Metadados salvos em {metadata_path}")
        except Exception as e:
            logger.error(f"Erro ao salvar metadados: {e}")
        
        return {
            "status": "success",
            "rendered": len(rendered_regions),
            "failed": len(failed_regions),
            "world": world_name
        }

    def get_save_worlds(self, pack_name, save_name):
        worlds_dir = os.path.join(self.storage.packs_dir, pack_name, "saves", save_name, "universe", "worlds")
        if not os.path.exists(worlds_dir): return []
        worlds_list = []
        try:
            for d in sorted(os.listdir(worlds_dir)):
                if os.path.isdir(os.path.join(worlds_dir, d)):
                    cp = os.path.join(worlds_dir, d, "chunks")
                    worlds_list.append({"id": d, "name": d, "has_chunks": os.path.exists(cp) and len(os.listdir(cp)) > 0})
        except: pass
        return worlds_list

    def get_map_manifest(self, pack_name, save_name, world_name=None):
        cache_dir = os.path.join(self.storage.packs_dir, pack_name, "saves", save_name, "map_cache")
        manifest = {"worlds": {}}
        if os.path.exists(cache_dir):
            for f in sorted(os.listdir(cache_dir)):
                if f.endswith(".json") and "." in f[:-5]:
                    try:
                        with open(os.path.join(cache_dir, f), "r") as j:
                            meta = json.load(j); w_id, rx, rz = meta.get("world", "default_world"), meta["rx"], meta["rz"]
                            if w_id not in manifest["worlds"]: manifest["worlds"][w_id] = {"min_x": rx, "max_x": rx, "min_z": rz, "max_z": rz, "regions": []}
                            manifest["worlds"][w_id]["regions"].append({"x": rx, "z": rz})
                            m = manifest["worlds"][w_id]
                            m["min_x"], m["max_x"], m["min_z"], m["max_z"] = min(m["min_x"], rx), max(m["max_x"], rx), min(m["min_z"], rz), max(m["max_z"], rz)
                    except: continue
        return {"status": "success", "manifest": manifest}
