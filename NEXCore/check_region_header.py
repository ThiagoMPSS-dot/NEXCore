
import struct

path = "/home/thiago/Documentos/NEXCore/data/packs/Teste/saves/New World/universe/worlds/instance-CreativeHub-d6bc9e57-af89-42f7-9f1c-6b7b78d4072d/chunks/5.4.region.bin"
with open(path, 'rb') as f:
    header = f.read(64)
    print(f"Header hex: {header.hex()}")
    
    f.seek(32) # Table starts at 32
    table_data = f.read(4096)
    
    # Try both big and little endian
    offsets_le = struct.unpack('<1024I', table_data)
    offsets_be = struct.unpack('>1024I', table_data)
    
    print("Searching for 4136 (absolute) or 1 (sector index) or 4 (if sector is 1024)")
    for i in range(1024):
        if offsets_le[i] in [4136, 4136//8, 4136//4096, 517]:
             print(f"LE Match at index {i}: {offsets_le[i]}")
        if offsets_be[i] in [4136, 4136//8, 4136//4096, 517]:
             print(f"BE Match at index {i}: {offsets_be[i]}")
             
    # Print first few non-zero entries
    for i in range(1024):
        if offsets_le[i] > 0:
            print(f"First non-zero LE: idx={i} val={offsets_le[i]} (hex={hex(offsets_le[i])})")
            break

    # Search for Zstandard magic 28 B5 2F FD
    f.seek(0)
    content = f.read(16384)
    magic = b'\x28\xb5\x2f\xfd'
    m_idx = content.find(magic)
    print(f"First Zstd magic found at: {m_idx}")
