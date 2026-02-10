
import os
import zstandard as zstd
import struct
import io
import binascii

def read_null_term_string(stream):
    b_str = bytearray()
    while True:
        b = stream.read(1)
        if not b or b == b'\x00': break
        b_str.append(ord(b))
    return b_str.decode('utf-8', 'ignore')

def decode_recursive(stream, end_pos, indent=0):
    while stream.tell() < end_pos:
        pos = stream.tell()
        tid_byte = stream.read(1)
        if not tid_byte: break
        tid = ord(tid_byte)
        if tid == 0: continue
        
        name = read_null_term_string(stream)
        
        if tid in [0x03, 0x04, 0x05]:
            size_data = stream.read(4)
            if len(size_data) < 4: break
            size = struct.unpack('<I', size_data)[0]
            
            print("  " * indent + f"[{hex(tid)}] {name} (Size: {size})")
            
            if tid in [0x03, 0x04]: # Containers
                decode_recursive(stream, stream.tell() + size, indent + 1)
            else: # Blob (0x05)
                # Show part of blob
                blob = stream.read(size)
                if size < 500:
                    print("  " * (indent+1) + f"BLOB: {binascii.hexlify(blob).decode()}")
        elif tid == 0x06:
            val = struct.unpack('<I', stream.read(4))[0]
            print("  " * indent + f"[{hex(tid)}] {name}: {val}")
        elif tid == 0x10:
            val = ord(stream.read(1))
            print("  " * indent + f"[{hex(tid)}] {name}: {val}")
        else:
            print("  " * indent + f"Unknown tag {hex(tid)} at {pos}")
            # Show following 16 bytes to debug
            stream.seek(pos)
            ctx = stream.read(16)
            print("  " * indent + f"Context Debug: {binascii.hexlify(ctx).decode()}")
            break

def decrypt_chunk():
    path = "/home/thiago/Documentos/NEXCore/data/packs/Teste/saves/New World/universe/worlds/instance-CreativeHub-d6bc9e57-af89-42f7-9f1c-6b7b78d4072d/chunks/5.4.region.bin"
    with open(path, 'rb') as f:
        data = f.read()
    
    magic = b'\x28\xb5\x2f\xfd'
    idx = data.find(magic, 4136)
    dctx = zstd.ZstdDecompressor()
    decompressed = dctx.decompress(data[idx:], max_output_size=1048576)
    stream = io.BytesIO(decompressed)
    total_size = struct.unpack('<I', stream.read(4))[0]
    decode_recursive(stream, total_size)

if __name__ == "__main__":
    decrypt_chunk()
