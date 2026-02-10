
import zstandard as zstd
import struct

path = 'data/packs/Teste/saves/New World/universe/worlds/zone3_taiga1_world/chunks/-1.-1.region.bin'
with open(path, 'rb') as f:
    f.seek(40+822*4)
    off = struct.unpack('>I', f.read(4))[0]
    byte_off = off * 4096 + 40
    f.seek(byte_off)
    data = f.read(1024*128)
    dctx = zstd.ZstdDecompressor()
    decomp = dctx.decompress(data, 1024*1024)

print(f"Total Size: {len(decomp)}")
# Print first 200 bytes with offsets
for i in range(0, 300, 16):
    chunk = decomp[i:i+16]
    hex_str = ' '.join(f'{b:02x}' for b in chunk)
    ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in chunk)
    print(f"{i:04x}: {hex_str:<48} | {ascii_str}")

def parse_ecs(data, start, limit):
    pos = start
    print("\nParsing tags with TID + Name + Size pattern:")
    while pos < limit:
        tag_start = pos
        tid = data[pos]
        if tid == 0 and pos + 1 < limit and data[pos+1] == 0: # End of container padding?
             pos += 1
             continue
             
        name = b""
        n_pos = pos + 1
        while n_pos < limit and data[n_pos] != 0:
            name += bytes([data[n_pos]])
            n_pos += 1
        name_str = name.decode('utf-8', errors='ignore')
        
        size_pos = n_pos + 1
        if size_pos + 4 > limit: break
        size = struct.unpack('<I', data[size_pos:size_pos+4])[0]
        
        print(f"[{tag_start:04x}] TID={tid:02x} NAME={name_str:<25} SIZE={size}")
        
        if tid == 0x03 or tid == 0x04: # Container
            # Stay at this level or enter? 
            # If we enter, we need recursion. For now just skip header.
            pos = size_pos + 4
        else:
            pos = size_pos + 4 + size

parse_ecs(decomp, 4, 400)
