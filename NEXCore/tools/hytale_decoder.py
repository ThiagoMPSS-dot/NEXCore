
import os
import zstandard as zstd
import struct
import io
import binascii

def read_varint(stream):
    value = 0
    shift = 0
    while True:
        b = stream.read(1)
        if not b: raise EOFError()
        byte = ord(b)
        value |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            break
        shift += 7
    return value

def parse_tag(stream):
    tag_id = stream.read(1)
    if not tag_id: return None
    t = ord(tag_id)
    
    # Heuristic based on observed dump:
    # 03: String
    # 04: Object/Struct?
    # 05: Data/Blob
    # 06: Int?
    # 10: Byte?
    
    # Read name (assuming it's a null-terminated or length-prefixed string)
    # The dump showed "Components" followed by size.
    # Actually, let's look at "BlockComponentChunk" 0x1b 0x00 0x00 0x00
    
    # Try reading as: TagID(1) Name([LenPrefixed]) Payload(...)
    
    name = ""
    # String tag (03) name logic
    # Wait, the dump had 03 [Name] [NullTerm?] 
    # Let's try to read name as UTF-8 until null or non-ascii
    name_bytes = bytearray()
    while True:
        b = stream.read(1)
        if not b or b == b'\x00': break
        name_bytes.append(ord(b))
    name = name_bytes.decode('utf-8', 'ignore')
    
    payload = None
    if t == 0x03:
         # String value follows?
         val_bytes = bytearray()
         while True:
             b = stream.read(1)
             if not b or b == b'\x00': break
             val_bytes.append(ord(b))
         payload = val_bytes.decode('utf-8', 'ignore')
    elif t == 0x05:
         # Blob follows?
         # Size LE 4 bytes
         size = struct.unpack('<I', stream.read(4))[0]
         stream.read(4) # Ignored 4 bytes (maybe type or offset?)
         payload = stream.read(size)
    elif t == 0x06:
         # Int?
         payload = struct.unpack('<I', stream.read(4))[0]
    elif t == 0x10:
         # Byte?
         payload = ord(stream.read(1))
         
    return {"tag": t, "name": name, "payload": payload}

def decrypt_chunk():
    path = "/home/thiago/Documentos/NEXCore/data/packs/Teste/saves/New World/universe/worlds/instance-CreativeHub-d6bc9e57-af89-42f7-9f1c-6b7b78d4072d/chunks/5.4.region.bin"
    with open(path, 'rb') as f:
        data = f.read()
    
    dctx = zstd.ZstdDecompressor()
    try:
        compressed = data[329527:]
        decompressed = dctx.decompress(compressed, max_output_size=1048576)
        stream = io.BytesIO(decompressed)
        
        # Skip header? (Header was b7cc0500 = size)
        stream.read(4)
        
        tags = []
        while stream.tell() < len(decompressed):
            try:
                tag = parse_tag(stream)
                if not tag: break
                
                # If name is empty and tag is unknown, we lost sync
                if not tag['name'] and tag['tag'] > 0x20:
                    print(f"Sync lost at {stream.tell()}")
                    break
                
                tags.append(tag)
                
                # Special case for "Components" - it contains nested tags?
                # Actually, let's just dump flat for now.
                
            except Exception as e:
                print(f"Error at {stream.tell()}: {e}")
                break
                
        # Filter and show
        for tag in tags:
            p_len = len(tag['payload']) if isinstance(tag['payload'], bytes) else tag['payload']
            print(f"[{tag['tag']}] {tag['name']}: {p_len}")
            if tag['name'] == "Sections":
                 print("  Sections found!")

    except Exception as e:
        print(f"Global error: {e}")

if __name__ == "__main__":
    decrypt_chunk()
