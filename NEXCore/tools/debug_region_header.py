
import os


# NOTE: standard python usually implies 'zstandard' library which might need install.
# If user doesn't have it, I can't run it.
# BUT, the user environment is Linux. 'pip install zstandard' might be needed.
# Converting to a check first.

try:
    import zstandard as zstd
except ImportError:
    print("zstandard library not found. Cannot decompress.")
    exit(1)

file_path = "/home/thiago/Documentos/HyPrism/data/packs/Teste/saves/New World/universe/worlds/flat_world/chunks/0.0.region.bin"

def analyze_header():
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    with open(file_path, "rb") as f:
        data = f.read(20000) # Read 20KB to ensure we get the full chunk header
    
    # Zstd Magic: 28 B5 2F FD
    zstd_sig = b'\x28\xb5\x2f\xfd'
    offset_zstd = data.find(zstd_sig)
    
    if offset_zstd != -1:
         print(f"Found ZSTD signature at offset {offset_zstd}")
         try:
             dctx = zstd.ZstdDecompressor()
             # decompressed = dctx.decompress(data[offset_zstd:], max_output_size=100000) 
             # stream reader is safer for partial data
             reader = dctx.stream_reader(data[offset_zstd:])
             decompressed = reader.read(256)
             
             print(f"Decompression successful!")
             print(f"Hex Start: {decompressed[:32].hex(' ')}")
             print(f"Text Start: {decompressed[:100]}")
         except Exception as e:
             print(f"Decompression failed: {e}")
    else:
         print("No ZSTD signature found in first 20KB for this attempt.")

if __name__ == "__main__":
    analyze_header()
