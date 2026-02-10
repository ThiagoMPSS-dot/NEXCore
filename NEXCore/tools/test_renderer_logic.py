
import os
import json
import zstandard as zstd
import io
import re
from collections import Counter

class MockStorage:
    def __init__(self):
        self.data_dir = "/home/thiago/Documentos/NEXCore/data"

def test_renderer_logic():
    storage = MockStorage()
    palette_path = os.path.join(storage.data_dir, "block_colors.json")
    block_palette = {}
    if os.path.exists(palette_path):
        with open(palette_path, 'r') as f:
            raw_palette = json.load(f)
            block_palette = {k.lower(): tuple(v) for k, v in raw_palette.items()}
    
    palette_lookup = {k.encode('utf-8'): k for k in block_palette.keys()}
    token_pattern = re.compile(b'[a-zA-Z0-9_:]{3,}')

    path = "/home/thiago/Documentos/NEXCore/data/packs/Teste/saves/New World/universe/worlds/instance-CreativeHub-d6bc9e57-af89-42f7-9f1c-6b7b78d4072d/chunks/5.4.region.bin"
    
    with open(path, 'rb') as f:
        # Scan for Zstd magic
        data = f.read()
        magic = b'\x28\xb5\x2f\xfd'
        idx = data.find(magic)
        if idx == -1:
            print("No Zstd found")
            return
        
        # Take first frame
        try:
            dctx = zstd.ZstdDecompressor()
            chunk_content = dctx.decompress(data[idx:], max_output_size=1048576)
            cdata_lower = chunk_content.lower()
            all_tokens = set(token_pattern.findall(cdata_lower))
            
            print(f"Total tokens found: {len(all_tokens)}")
            print("First 20 tokens:", list(all_tokens)[:20])
            
            found_blocks = []
            for p_encoded, p_key in palette_lookup.items():
                if p_encoded in all_tokens:
                    found_blocks.append(p_key)
            
            print(f"Found {len(found_blocks)} matching palette keys")
            print("Top matches:", found_blocks[:20])
            
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    test_renderer_logic()
