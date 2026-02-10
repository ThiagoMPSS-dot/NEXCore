
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

def dump_all_tags(stream, end_pos, indent=0):
    while stream.tell() < end_pos:
        tid_byte = stream.read(1)
        if not tid_byte: break
        tid = ord(tid_byte)
        name = read_null_term_string(stream)
        
        if tid in [0x03, 0x04, 0x05]:
            header = stream.read(8)
            size, unknown = struct.unpack('<II', header)
            print("  " * indent + f"[{hex(tid)}] {name} (Size: {size})")
            
            if tid in [0x03, 0x04]:
                dump_all_tags(stream, stream.tell() + size, indent + 1)
            else:
                # For blobs, print size and first 16 bytes
                blob = stream.read(size)
                print("  " * (indent+1) + f"BLOB START: {binascii.hexlify(blob[:16]).decode()}")
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

    magic = b'\x28\xb5\x2f\xfd'
    idx = data.find(magic, 4136) # Start at first known frame
    
    if idx != -1:
        try:
            dctx = zstd.ZstdDecompressor()
            decompressed = dctx.decompress(data[idx:], max_output_size=1048576)
            stream = io.BytesIO(decompressed)
            total_size = struct.unpack('<I', stream.read(4))[0]
            
            import sys
            with open("full_dump.txt", "w") as f_out:
                # Redirect stdout for convenience or just call with f_out
                # I'll just rewrite dump_all_tags to take a file
                pass
            
            # Re-running dump logic into file
            def dump_to_file(stream, end_pos, f_out, indent=0):
                while stream.tell() < end_pos:
                    tid_byte = stream.read(1)
                    if not tid_byte: break
                    tid = ord(tid_byte)
                    name = read_null_term_string(stream)
                    if tid in [0x03, 0x04, 0x05]:
                        header = stream.read(8)
                        size, unk = struct.unpack('<II', header)
                        f_out.write("  " * indent + f"[{hex(tid)}] {name} (Size: {size})\n")
                        if tid in [0x03, 0x04]:
                            dump_to_file(stream, stream.tell() + size, f_out, indent + 1)
                        else:
                            # Blob
                            blob = stream.read(size)
                            if name == "Palette":
                                f_out.write("  " * (indent+1) + f"PALETTE: {binascii.hexlify(blob).decode()}\n")
                            else:
                                f_out.write("  " * (indent+1) + f"BLOB START: {binascii.hexlify(blob[:16]).decode()}\n")
                    elif tid == 0x06:
                        val = struct.unpack('<I', stream.read(4))[0]
                        f_out.write("  " * indent + f"[{hex(tid)}] {name}: {val}\n")
                    elif tid == 0x10:
                        val = ord(stream.read(1))
                        f_out.write("  " * indent + f"[{hex(tid)}] {name}: {val}\n")
                    else: break
            
            with open("full_dump.txt", "w") as f_out:
                dump_to_file(stream, total_size, f_out)
            print("Full dump saved to full_dump.txt")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    analyze()
