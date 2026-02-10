
import os
import sys
import json

# Add project root to path
sys.path.append("/home/thiago/Documentos/NEXCore")

from nexcore.map_renderer import MapRenderer

class MockStorage:
    def __init__(self):
        self.data_dir = "/home/thiago/Documentos/NEXCore/data"
        self.packs_dir = "/home/thiago/Documentos/NEXCore/data/packs"

storage = MockStorage()
renderer = MapRenderer(storage)

worlds = ["zone3_taiga1_world", "default_world"]
for world in worlds:
    print(f"\n--- Testing world: {world} ---")
    result = renderer.render_region_tile("Teste", "New World", -1, -1, world)
    print(f"Result: {result}")
    
    cache_file = f"data/packs/Teste/saves/New World/map_cache/-1.-1.json"
    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            meta = json.load(f)
            # Find palette entry
            palette = meta.get("palette", [])
            print(f"Sample palette blocks: {palette[:10]}")
