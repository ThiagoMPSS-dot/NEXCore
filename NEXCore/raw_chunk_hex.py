
import os
import zstandard as zstd
import binascii

def analyze_raw_decompressed():
    path = "/home/thiago/Documentos/NEXCore/data/packs/Teste/saves/New World/universe/worlds/instance-CreativeHub-d6bc9e57-af89-42f7-9f1c-6b7b78d4072d/chunks/5.4.region.bin"
    with open(path, 'rb') as f:
        data = f.read()

    magic = b'\x28\xb5\x2f\xfd'
    idx = data.find(magic, 4136)
    
    if idx != -1:
        dctx = zstd.ZstdDecompressor()
        decompressed = dctx.decompress(data[idx:], max_output_size=1048576)
        print(f"Hex Dump (first 256 bytes):")
        print(binascii.hexlify(decompressed[:256]).decode())

if __name__ == "__main__":
    analyze_raw_decompressed()
