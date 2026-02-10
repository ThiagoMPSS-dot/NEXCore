
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

path = "/home/thiago/Documentos/NEXCore/data/packs/Teste/saves/New World/universe/worlds/zone3_taiga1_world/chunks/-1.-1.region.bin"

def find_data_paths(tags, path=""):
    found = []
    for k, v in tags.items():
        curr_path = f"{path}/{k}"
        if isinstance(v, dict):
            found.extend(find_data_paths(v, curr_path))
        elif isinstance(v, list):
            for i, i_val in enumerate(v):
                if isinstance(i_val, dict):
                    found.extend(find_data_paths(i_val, f"{curr_path}/{i}"))
        elif k == "Data" and isinstance(v, bytes) and len(v) == 16384:
            found.append(curr_path)
    return found

with open(path, 'rb') as f:
    f.seek(40 + 822*4)
    off = struct.unpack('>I', f.read(4))[0]
    byte_off = off * 4096 + 40
    f.seek(byte_off)
    data = f.read(256000)
    dctx = zstd.ZstdDecompressor()
    decompressed = dctx.decompress(data, max_output_size=1048576)
    stream = io.BytesIO(decompressed)
    total_size = struct.unpack('<I', stream.read(4))[0]
    ecs = renderer._decode_ecs_recursive(stream, total_size)
    
    paths = find_data_paths(ecs)
    print("Paths to 16384-byte Data blobs:")
    for p in paths:
        print(f"  {p}")

