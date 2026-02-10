
import os
import zstandard as zstd
import binascii
import re
import struct

def analyze_tag_headers():
    path = "/home/thiago/Documentos/NEXCore/data/packs/Teste/saves/New World/universe/worlds/instance-CreativeHub-d6bc9e57-af89-42f7-9f1c-6b7b78d4072d/chunks/5.4.region.bin"
    with open(path, 'rb') as f:
        data = f.read()

    magic = b'\x28\xb5\x2f\xfd'
    idx = data.find(magic, 4136)
    dctx = zstd.ZstdDecompressor()
    decompressed = dctx.decompress(data[idx:], max_output_size=1048576)
    
    # Names we are interested in
    targets = [b'Components', b'BlockComponentChunk', b'BlockComponents', b'ChunkColumn', b'Sections', b'Block', b'Data', b'Version']
    
    for t in targets:
        print(f"\n--- Analyzing target: {t.decode()} ---")
        matches = list(re.finditer(re.escape(t + b'\x00'), decompressed))
        for m in matches[:5]:
            start = m.start()
            pre = decompressed[max(0, start-4):start]
            post = decompressed[m.end():m.end()+12]
            print(f"  At {start}: Pre={binascii.hexlify(pre).decode()} Post={binascii.hexlify(post).decode()}")

if __name__ == "__main__":
    analyze_tag_headers()
