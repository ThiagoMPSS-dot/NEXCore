
import struct
import zstandard as zstd
import io

path = '/home/thiago/Documentos/NEXCore/data/packs/Teste/saves/New World/universe/worlds/default_world/chunks/-1.-1.region.bin'
with open(path, 'rb') as f:
    f.seek(40 + 565*4)
    off = struct.unpack('>I', f.read(4))[0]
    byte_off = off * 4096 + 40
    f.seek(byte_off)
    data = f.read(1024*256)
    dctx = zstd.ZstdDecompressor()
    decomp = dctx.decompress(data, 1024*1024)

print(f"Total size: {len(decomp)}")
# Print first 500 bytes with analysis
i = 4
limit = 500
while i < limit:
    tid = decomp[i]
    name = b""
    n_pos = i + 1
    while n_pos < len(decomp) and decomp[n_pos] != 0:
        name += bytes([decomp[n_pos]])
        n_pos += 1
    name_str = name.decode('utf-8', errors='ignore')
    
    size_pos = n_pos + 1
    size = struct.unpack('<I', decomp[size_pos:size_pos+4])[0]
    print(f"[{i:04x}] TID:{tid:02x} NAME:{name_str:<25} SIZE:{size}")
    
    if tid in [0x03, 0x04]:
        i = size_pos + 4 # Move into or skip header
    else:
        i = size_pos + 4 + size
