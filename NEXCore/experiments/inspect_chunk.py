
import zstandard as zstd
import os

REGION_FILE = "/home/thiago/Documentos/HyPrism/data/packs/Teste/saves/New World/universe/worlds/flat_world/chunks/0.0.region.bin"

def inspect_chunk():
    if not os.path.exists(REGION_FILE):
        print("Region file not found")
        return

    with open(REGION_FILE, 'rb') as f:
        # Seek to first ZSTD frame
        f.seek(4136)
        data = f.read() # Read all remaining data?
        
    try:
        dctx = zstd.ZstdDecompressor()
        # Try to decompress stream
        decompressed = dctx.decompress(data, max_output_size=1024*1024*10) # 10MB limit
        
        print(f"Decompressed {len(decompressed)} bytes.")
        print("First 100 bytes (Hex):")
        print(decompressed[:100].hex())
        print("First 100 bytes (Text):")
        print(decompressed[:100])
        
        # Check for strings
        import re
        strings = re.findall(b'[a-zA-Z0-9_]{3,}', decompressed[:2000])
        print(f"Strings found: {strings[:20]}")
        
    except Exception as e:
        print(f"Decompression error: {e}")

if __name__ == "__main__":
    inspect_chunk()
