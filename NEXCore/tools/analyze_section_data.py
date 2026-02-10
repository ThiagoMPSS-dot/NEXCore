
import os
import zstandard as zstd
import struct
import io
import binascii

def analyze_section_data():
    path = "/home/thiago/Documentos/NEXCore/data/packs/Teste/saves/New World/universe/worlds/instance-CreativeHub-d6bc9e57-af89-42f7-9f1c-6b7b78d4072d/chunks/5.4.region.bin"
    
    with open(path, 'rb') as f:
        data = f.read()
    
    dctx = zstd.ZstdDecompressor()
    try:
        compressed = data[329527:]
        decompressed = dctx.decompress(compressed, max_output_size=1048576)
        
        # We saw "Block" tag and then "Data" d8 2f 00 00 (size 12248)
        data_tag = b'\x05\x44\x61\x74\x61\x00'
        
        # Let's find all occurrences and analyze sizes
        start = 0
        section_id = 0
        while True:
            idx = decompressed.find(data_tag, start)
            if idx == -1: break
            
            header = decompressed[idx+6:idx+14]
            size = struct.unpack('<I', header[:4])[0]
            
            if size == 12248:
                print(f"Found Section {section_id} Block Data at {idx}, size {size}")
                content = decompressed[idx+14:idx+14+size]
                
                # Analyze bit patterns
                # If 6 bits, let's look at the first few bytes
                # 16384 blocks * 6 bits = 98304 bits = 12288 bytes.
                # Matches exactly!
                
                # Check for palette inside this section?
                # Usually sections have a local palette IF bit-width is small.
                # Look for a tag BEFORE "Block" that might be "Palette"
                preview = decompressed[idx-100:idx]
                print(f"  Pre-tag context: {binascii.hexlify(preview).decode()}")
                
                # See if there are strings in the preview
                import re
                strings = re.findall(b'[a-zA-Z]{3,}', preview)
                print(f"  Strings in pre-tag: {strings}")
                
            start = idx + 1
            section_id += 1
            if section_id > 20: break

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    analyze_section_data()
