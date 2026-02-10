
import zstandard as zstd
import struct

base_dir = '/home/thiago/Documentos/NEXCore/data/packs/Teste/saves/New World/universe/worlds/'
for world in os.listdir(base_dir):
    path = os.path.join(base_dir, world, 'chunks', '-1.-1.region.bin')
    if not os.path.exists(path): continue
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
        
        if not decomp: continue

def find_all(s):
    idx = 0
    while True:
        idx = decomp.find(s, idx)
        if idx == -1: break
        print(f"\n--- Found '{s.decode() if isinstance(s, bytes) else s}' at {idx} ---")
        start = max(0, idx - 20)
        end = min(len(decomp), idx + len(s) + 20)
        chunk = decomp[start:end]
        hex_str = ' '.join(f'{b:02x}' for b in chunk)
        ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in chunk)
        print(f"Hex: {hex_str}")
        print(f"Asc: {ascii_str}")
        # Mark the actual start of search term in hex
        rel_idx = idx - start
        marker = ' ' * (rel_idx * 3) + '^^'
        print(f"     {marker}")
        idx += 1

find_all(b'EnvironmentChunk\x00')
find_all(b'Data\x00')
find_all(b'Palette\x00')
find_all(b'Sections\x00')
find_all(b'\x1b\x60\x00\x00') # 24603
