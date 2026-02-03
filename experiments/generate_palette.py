
import zipfile
import json
import os
from PIL import Image
import io

ASSETS_PATH = "/home/thiago/.var/app/com.hypixel.HytaleLauncher/data/Hytale/install/release/package/game/latest/Assets.zip"
OUTPUT_FILE = "data/block_colors.json"

def generate_palette():
    if not os.path.exists(ASSETS_PATH):
        print(f"Error: Assets not found at {ASSETS_PATH}")
        return

    palette = {}
    
    with zipfile.ZipFile(ASSETS_PATH, 'r') as z:
        for file_info in z.infolist():
            if file_info.filename.startswith("Common/BlockTextures/") and file_info.filename.endswith(".png"):
                # Extract Block Name (e.g. Common/BlockTextures/Grass_Top.png -> Grass_Top)
                name = os.path.basename(file_info.filename).replace(".png", "")
                
                try:
                    with z.open(file_info) as f:
                        img = Image.open(f).convert('RGB')
                        # Resizing to 1x1 is a fast way to get average color
                        avg_color = img.resize((1, 1)).getpixel((0, 0))
                        palette[name] = avg_color
                except Exception as e:
                    print(f"Skipping {name}: {e}")

    print(f"Generated palette with {len(palette)} entries.")
    
    # Save to data folder of the project? Or just print for now? 
    # Let's save to current working directory or a temp location
    with open("block_colors.json", "w") as f:
        json.dump(palette, f, indent=2)

if __name__ == "__main__":
    generate_palette()
