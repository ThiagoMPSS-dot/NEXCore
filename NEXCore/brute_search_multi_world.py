
import os
import zstandard as zstd
import struct

base_dir = '/home/thiago/Documentos/NEXCore/data/packs/Teste/saves/New World/universe/worlds/'
target_worlds = ['default', 'default_world', 'zone3_taiga1_world']

for world in target_worlds:
    path = os.path.join(base_dir, world, 'chunks', '-1.-1.region.bin')
    if not os.path.exists(path): 
        print(f"Skipping {world} - path not found")
        continue

    print(f"\n\n==== SEARCHING WORLD: {world} ====")
    with open(path, 'rb') as f:
        f.seek(40)
        idx = 0
        decomp = None
        while idx < 1024:
            off_data = f.read(4)
            if not off_data: break
            off = struct.unpack('>I', off_data)[0]
            if off > 0:
                byte_off = off * 4096 + 40
                pos = f.tell()
                f.seek(byte_off)
                data = f.read(1024*256)
                try:
                    dctx = zstd.ZstdDecompressor()
                    decomp = dctx.decompress(data, 1024*1024)
                    print(f"Found valid chunk at table index {idx}")
                    break
                except: pass
                f.seek(pos)
            idx += 1
        
        if not decomp: 
            print("No valid compressed chunks found.")
            continue

        def find_all(s, label):
            count = 0
            idx_search = 0
            while True:
                idx_search = decomp.find(s, idx_search)
                if idx_search == -1: break
                count += 1
                print(f"  [{label}] Found at {idx_search}: {decomp[idx_search-10:idx_search+30].hex()}")
                idx_search += 1
            if count == 0:
                 print(f"  [{label}] Not found.")

        find_all(b'EnvironmentChunk\x00', "EnvChunk")
        find_all(b'Sections\x00', "Sections")
        find_all(b'Data\x00', "Data")
        find_all(b'Palette\x00', "Palette")
        find_all(b'\x1b\x60\x00\x00', "Size24603")
