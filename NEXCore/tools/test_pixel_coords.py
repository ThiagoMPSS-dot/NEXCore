
import sys
sys.path.append('/home/thiago/Documentos/NEXCore')

from nexcore.storage import StorageManager
from nexcore.map_renderer import MapRenderer
from PIL import Image

# Criar renderer
s = StorageManager('/home/thiago/Documentos/NEXCore/data')
r = MapRenderer(s)

# Criar uma imagem de teste
img = Image.new('RGB', (1024, 1024), color=(20, 20, 25))
pixels = img.load()

# Simular o cálculo de coordenadas para chunk_lx=0, chunk_lz=0
chunk_lx, chunk_lz = 0, 0
base_x, base_z = chunk_lx * 32, chunk_lz * 32

print(f"Chunk local ({chunk_lx}, {chunk_lz})")
print(f"Base coords: ({base_x}, {base_z})")

# Testar alguns pixels
for lz in range(5):
    for lx in range(5):
        px, pz = base_x + lx, base_z + lz
        print(f"  Local ({lx}, {lz}) -> Pixel ({px}, {pz})")
        pixels[px, pz] = (255, 0, 0)  # Vermelho

# Agora testar chunk no canto oposto
chunk_lx, chunk_lz = 31, 31
base_x, base_z = chunk_lx * 32, chunk_lz * 32

print(f"\nChunk local ({chunk_lx}, {chunk_lz})")
print(f"Base coords: ({base_x}, {base_z})")

for lz in range(5):
    for lx in range(5):
        px, pz = base_x + lx, base_z + lz
        print(f"  Local ({lx}, {lz}) -> Pixel ({px}, {pz})")
        if px < 1024 and pz < 1024:
            pixels[px, pz] = (0, 255, 0)  # Verde
        else:
            print(f"    FORA DOS LIMITES!")

img.save('/tmp/test_coords.png')
print("\nImagem salva em /tmp/test_coords.png")
