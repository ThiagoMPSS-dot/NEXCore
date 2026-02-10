
import os
import struct
import io
import zstandard as zstd
import sys
sys.path.append("/home/thiago/Documentos/NEXCore")
from nexcore.map_renderer import MapRenderer

class MockStorage:
    def __init__(self):
        self.data_dir = "/home/thiago/Documentos/NEXCore/data"
        self.packs_dir = "/home/thiago/Documentos/NEXCore/data/packs"

storage = MockStorage()
renderer = MapRenderer(storage)

path = '/home/thiago/Documentos/NEXCore/data/packs/Teste/saves/New World/universe/worlds/default/chunks/-1.-1.region.bin'
if not os.path.exists(path):
    print(f"Path not found: {path}")
    sys.exit(1)

with open(path, 'rb') as f:
    f.seek(40)
    for idx in range(1024):
        off_data = f.read(4)
        if not off_data: break
        off = struct.unpack('>I', off_data)[0]
        if off == 0: continue
        
        byte_off = off * 4096 + 40
        f_pos = f.tell()
        f.seek(byte_off)
        data = f.read(1024*256)
        try:
            dctx = zstd.ZstdDecompressor()
            decomp = dctx.decompress(data, 1024*1024)
            print(f"\n--- Chunk {idx} at {byte_off} ---")
            stream = io.BytesIO(decomp)
            total_size = struct.unpack('<I', stream.read(4))[0]
            ecs = renderer._decode_ecs_recursive(stream, 4 + total_size)
            
            def print_tags_compact(tags, path=""):
                for k, v in tags.items():
                    p = f"{path}/{k}"
                    if isinstance(v, dict):
                        print(f"  Container: {p}")
                        if "Environment" in k or "Block" in k or "Section" in k or "Palette" in k:
                             print_tags_compact(v, p)
                    else:
                        print(f"  Tag: {p} ({type(v).__name__}) size={len(v) if isinstance(v, bytes) else '-'}")

            print_tags_compact(ecs)
            # Break after first few valid chunks
            if idx > 100: break 
        except Exception as e:
            # print(f"Error at {idx}: {e}")
            pass
        f.seek(f_pos)
