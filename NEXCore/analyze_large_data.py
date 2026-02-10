
import os
import zstandard as zstd
import struct
import io
import binascii

def analyze_large_data():
    path = "/home/thiago/Documentos/NEXCore/data/packs/Teste/saves/New World/universe/worlds/instance-CreativeHub-d6bc9e57-af89-42f7-9f1c-6b7b78d4072d/chunks/5.4.region.bin"
    
    with open(path, 'rb') as f:
        # We'll search for the tag again to be sure
        data = f.read()
    
    data_tag = b'\x05\x44\x61\x74\x61\x00'
    idx = data.find(data_tag, 329527 - 100) # Start near where we saw it
    if idx == -1:
        # Try finding the first large one
        start = 0
        while True:
            idx = data.find(data_tag, start)
            if idx == -1: break
            header = data[idx+6:idx+14]
            size = struct.unpack('<I', header[:4])[0]
            if size > 10000:
                print(f"Found large Data at {idx}, size {size}")
                break
            start = idx + 1
            
    if idx == -1:
        print("Large data not found")
        return

    payload_start = idx + 6 + 4 # Skip tag and size
    content = data[payload_start:payload_start + 4000] # Read 4kb
    print(f"Content Hex (first 512 bytes):")
    print(binascii.hexlify(content[:512]).decode())
    
    # Check for patterns
    # Is it a sequence of shorts? 
    shorts = struct.unpack(f'<{len(content[:512])//2}H', content[:512])
    print("As shorts:", shorts[:50])
    
    # Is it a sequence of bytes?
    print("As bytes:", list(content[:50]))

if __name__ == "__main__":
    analyze_large_data()
