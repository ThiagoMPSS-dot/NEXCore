
import struct
import os

REGION_FILE = "/home/thiago/Documentos/HyPrism/data/packs/Teste/saves/New World/universe/worlds/flat_world/chunks/0.0.region.bin"

def inspect_header():
    if not os.path.exists(REGION_FILE):
        print("Region file not found")
        return

    with open(REGION_FILE, 'rb') as f:
        # Signature 20 bytes
        sig = f.read(20)
        print(f"Signature: {sig}")
        
        # Maybe version?
        version = f.read(4)
        print(f"Version/Unknown at 20: {version.hex()}") # 00000001?
        
        # Table of 1024 entries? (32x32)
        # Each entry maybe 4 bytes (offset) + 4 bytes (size)? or just offset?
        # If chunks are packed, offset is enough? Or maybe size and offset.
        # Let's read 1024 * 4 bytes first.
        
        table_data = f.read(1024 * 4)
        offsets = struct.unpack(f'>{1024}I', table_data)
        
        print("First 16 offsets:")
        for i in range(16):
            print(f"Chunk {i}: {offsets[i]}")
            
        print("...")
        
        # Calculate possible start of data
        current_pos = f.tell()
        print(f"Current File Position (end of table): {current_pos}")
        
        # If header ends here, it should be around 4120. (20 + 4 + 4096 = 4120)
        # Inspect a bit more
        more = f.read(32)
        print(f"Bytes after table: {more.hex()}")

if __name__ == "__main__":
    inspect_header()
