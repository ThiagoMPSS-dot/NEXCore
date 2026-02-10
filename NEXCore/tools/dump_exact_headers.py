
import zstandard as zstd
import struct

path = 'data/packs/Teste/saves/New World/universe/worlds/zone3_taiga1_world/chunks/-1.-1.region.bin'
with open(path, 'rb') as f:
    f.seek(40+822*4)
    off = struct.unpack('>I', f.read(4))[0]
    byte_off = off * 4096 + 40
    f.seek(byte_off)
    data = f.read(1024*256)
    dctx = zstd.ZstdDecompressor()
    decomp = dctx.decompress(data, 1024*1024)

def dump_at(name, s_bytes):
    idx = decomp.find(s_bytes)
    if idx == -1: return
    print(f"\n--- Tag: {name} at {idx} ---")
    # TID is byte before
    tid_idx = idx - 1
    tid = decomp[tid_idx]
    # Size is after name+null
    size_idx = idx + len(s_bytes)
    size = struct.unpack('<I', decomp[size_idx:size_idx+4])[0]
    print(f"TID: 0x{tid:02x}")
    print(f"Size field: {size}")
    print(f"Next 20 bytes: {decomp[size_idx+4:size_idx+24].hex()}")

dump_at("Components", b"Components\x00")
dump_at("BlockComponentChunk", b"BlockComponentChunk\x00")
dump_at("BlockComponents", b"BlockComponents\x00")
dump_at("EnvironmentChunk", b"EnvironmentChunk\x00")
dump_at("Sections", b"Sections\x00")
