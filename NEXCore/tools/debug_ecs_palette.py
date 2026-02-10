
import zstandard as zstd
import struct
import io
import sys
sys.path.append("/home/thiago/Documentos/NEXCore")
from nexcore.map_renderer import MapRenderer

class MockStorage:
    def __init__(self):
        self.data_dir = "/home/thiago/Documentos/NEXCore/data"
        self.packs_dir = "/home/thiago/Documentos/NEXCore/data/packs"

storage = MockStorage()
renderer = MapRenderer(storage)

path = '/home/thiago/Documentos/NEXCore/data/packs/Teste/saves/New World/universe/worlds/zone3_taiga1_world/chunks/-1.-1.region.bin'
with open(path, 'rb') as f:
    f.seek(40+822*4)
    off = struct.unpack('>I', f.read(4))[0]
    byte_off = off * 4096 + 40
    f.seek(byte_off)
    data = f.read(1024*256)
    dctx = zstd.ZstdDecompressor()
    decomp = dctx.decompress(data, 1024*1024)
    
    stream = io.BytesIO(decomp)
    total_size = struct.unpack('<I', stream.read(4))[0]
    ecs = renderer._decode_ecs_recursive(stream, 4 + total_size)
    
    root = ecs.get("Components", {}).get("BlockComponentChunk", {})
    env = root.get("EnvironmentChunk", {})
    col = env.get("ChunkColumn", {})
    sections = col.get("Sections", {})
    
    # Dump Palette of first section
    if sections:
         keys = sorted(sections.keys(), key=lambda k: int(k) if k.isdigit() else 0)
         first_sec = sections[keys[0]]
         chunk_sec = first_sec.get("Components", {}).get("ChunkSection", {})
         block = chunk_sec.get("Block", {})
         palette = block.get("Palette", {})
         print(f"Palette Type: {type(palette)}")
         if isinstance(palette, dict):
             print(f"Palette Size: {len(palette)}")
             for k in sorted(palette.keys(), key=lambda x: int(x) if x.isdigit() else 0)[:10]:
                 print(f"  {k}: {palette[k]}")
         else:
             print(f"Palette Data: {palette}")
