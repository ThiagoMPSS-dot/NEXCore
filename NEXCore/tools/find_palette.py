
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

def dump_tags(stream, end_pos, indent=0):
    while stream.tell() < end_pos:
        tid_byte = stream.read(1)
        if not tid_byte: break
        tid = ord(tid_byte)
        name = read_null_term_string(stream)
        
        if tid in [0x03, 0x04, 0x05]:
            header = stream.read(8)
            size, unknown = struct.unpack('<II', header)
            print("  " * indent + f"[{hex(tid)}] {name} (Size: {size})")
            
            if name == "Data":
                stream.seek(size, 1)
            elif name == "Palette":
                # DUMP PALETTE!
                blob = stream.read(size)
                print("  " * (indent+1) + f"PALETTE BLOB: {binascii.hexlify(blob).decode()}")
            elif tid in [0x03, 0x04]:
                dump_tags(stream, stream.tell() + size, indent + 1)
            else:
                stream.seek(size, 1)
        elif tid == 0x06:
            val = struct.unpack('<I', stream.read(4))[0]
            print("  " * indent + f"[{hex(tid)}] {name}: {val}")
        elif tid == 0x10:
            val = ord(stream.read(1))
            print("  " * indent + f"[{hex(tid)}] {name}: {val}")
        else:
            break

def analyze():
    path = "/home/thiago/Documentos/NEXCore/data/packs/Teste/saves/New World/universe/worlds/instance-CreativeHub-d6bc9e57-af89-42f7-9f1c-6b7b78d4072d/chunks/5.4.region.bin"
    with open(path, 'rb') as f:
        data = f.read()
    dctx = zstd.ZstdDecompressor()
    compressed = data[329527:]
    decompressed = dctx.decompress(compressed, max_output_size=1048576)
    stream = io.BytesIO(decompressed)
    total_size = struct.unpack('<I', stream.read(4))[0]
    dump_tags(stream, total_size)

if __name__ == "__main__":
    analyze()
