
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

print("\n--- Testing get_save_worlds ---")
worlds = renderer.get_save_worlds("Teste", "New World")
print(json.dumps(worlds, indent=2))
