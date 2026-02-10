
import os
import zstandard as zstd
import struct

base_dir = '/home/thiago/Documentos/NEXCore/data/packs/Teste/saves/New World/universe/worlds/'
worlds = os.listdir(base_dir)

for world in worlds:
    path = os.path.join(base_dir, world, 'chunks', '-1.-1.region.bin')
    if not os.path.exists(path): continue

    print(f"\nWORLD: {world}")
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
                f.seek(byte_off)
                data = f.read(1024*256)
                try:
                    dctx = zstd.ZstdDecompressor()
                    decomp = dctx.decompress(data, 1024*1024)
                    break
                except: pass
            idx += 1
        
        if not decomp: continue

        # Search for tags and sizes
        tags_of_interest = [b'EnvironmentChunk\x00', b'Sections\x00', b'Data\x00', b'Palette\x00']
        for tag in tags_of_interest:
            pos = decomp.find(tag)
            if pos > -1:
                # Get size around it
                # For TID + Name + Size, size is 4 bytes after Name+Null
                size_pos = pos + len(tag)
                if size_pos + 4 <= len(decomp):
                    size = struct.unpack('<I', decomp[size_pos:size_pos+4])[0]
                    print(f"  {tag.decode().strip(chr(0))}: Found at {pos}, Size={size}")
                else:
                    print(f"  {tag.decode().strip(chr(0))}: Found at {pos}, End of buffer")
            else:
                pass
