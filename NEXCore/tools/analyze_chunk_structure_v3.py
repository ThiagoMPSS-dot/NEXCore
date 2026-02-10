
import os
import zstandard as zstd
import struct
import io
import binascii

def analyze_chunk_structure():
    path = "/home/thiago/Documentos/NEXCore/data/packs/Teste/saves/New World/universe/worlds/instance-CreativeHub-d6bc9e57-af89-42f7-9f1c-6b7b78d4072d/chunks/5.4.region.bin"
    
    with open(path, 'rb') as f:
        data = f.read()
    
    # Found frame start at 329527 earlier
    dctx = zstd.ZstdDecompressor()
    try:
        compressed = data[329527:]
        decompressed = dctx.decompress(compressed, max_output_size=1048576)
        print(f"Decompressed frame size: {len(decompressed)}")
        
        # Find "Block" tag
        block_tag = b'\x03\x42\x6c\x6f\x63\x6b\x00' # "Block" string tag
        b_idx = decompressed.find(block_tag)
        if b_idx != -1:
            print(f"Found 'Block' tag at {b_idx}")
            # Look at context around it
            ctx = decompressed[b_idx-16:b_idx+100]
            print(f"Context: {binascii.hexlify(ctx).decode()}")
        
        # Look for the LARGE Data section we saw before
        data_tag = b'\x05\x44\x61\x74\x61\x00'
        d_idx = decompressed.find(data_tag)
        if d_idx != -1:
            print(f"Found 'Data' tag at {d_idx}")
            header = decompressed[d_idx:d_idx+32]
            print(f"Data Header Hex: {binascii.hexlify(header).decode()}")
            
            # The pattern was: 05 44 61 74 61 00 [Size LE 4 bytes] [??? 4 bytes] [Payload...]
            # 05 44 61 74 61 00 5e 9a 00 00 00 00 00 00 ...
            # Size = 0x9a5e = 39518.
            
            payload = decompressed[d_idx+14:d_idx+14+1024]
            print(f"Payload Start Hex: {binascii.hexlify(payload).decode()}")
            
            # Let's see if 1.2 bits/block makes sense for bit-packing.
            # If we use 8 bits for palette index, and a small palette...
            
            # Check for "Palette" again, but maybe it's not a string?
            # Maybe it's a list of IDs?
            # Look for 0x01 (List) followed by some size.
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    analyze_chunk_structure()
