
import zstandard as zstd
import struct
import io

path = 'data/packs/Teste/saves/New World/universe/worlds/zone3_taiga1_world/chunks/-1.-1.region.bin'
with open(path, 'rb') as f:
    f.seek(40+822*4)
    off = struct.unpack('>I', f.read(4))[0]
    byte_off = off * 4096 + 40
    f.seek(byte_off)
    data = f.read(1024*256)
    dctx = zstd.ZstdDecompressor()
    decomp = dctx.decompress(data, 1024*1024)

def dump_near(s_name, s_bytes):
    idx = decomp.find(s_bytes)
    if idx > -1:
        print(f"\n--- Found '{s_name}' at {idx} ---")
        before = decomp[idx-20:idx]
        after = decomp[idx+len(s_bytes):idx+len(s_bytes)+30]
        # TID is likely the byte exactly before the name
        tid = decomp[idx-1]
        print(f"TID: {tid:02x}")
        print(f"Bytes before: {before.hex()}")
        print(f"Bytes after:  {after.hex()}")
        # Check if 4 bytes after Name+Null look like a size
        null_idx = idx + len(s_bytes)
        if decomp[null_idx] == 0:
            size_bytes = decomp[null_idx+1:null_idx+5]
            size = struct.unpack('<I', size_bytes)[0]
            print(f"Potential Size (after name): {size}")
        # Check if 4 bytes before TID look like a size
        size_bytes_before = decomp[idx-5:idx-1]
        size_before = struct.unpack('<I', size_bytes_before)[0]
        print(f"Potential Size (before TID): {size_before}")

dump_near("Sections", b"Sections\0")
dump_near("Palette", b"Palette\0")
dump_near("Data", b"Data\0")
dump_near("ChunkSection", b"ChunkSection\0")
