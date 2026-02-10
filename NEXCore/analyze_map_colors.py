
from PIL import Image
import sys

img_path = '/home/thiago/Documentos/NEXCore/data/packs/Teste/saves/New World/map_cache/-1.-1.png'
img = Image.open(img_path)
pixels = img.load()

# Contar cores
color_counts = {}
for y in range(1024):
    for x in range(1024):
        color = pixels[x, y]
        if color not in color_counts:
            color_counts[color] = 0
        color_counts[color] += 1

# Ordenar por contagem
sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)

print(f"Análise de cores da imagem {img_path}")
print(f"Total de pixels: {1024*1024}")
print(f"\nTop 10 cores mais comuns:")
for i, (color, count) in enumerate(sorted_colors[:10]):
    pct = (count / (1024*1024)) * 100
    print(f"  {i+1}. RGB{color}: {count:,} pixels ({pct:.2f}%)")

# Verificar se há pixels não-fundo
background = (20, 20, 25)
non_bg_count = sum(count for color, count in color_counts.items() if color != background)
print(f"\nPixels não-fundo: {non_bg_count:,} ({(non_bg_count/(1024*1024))*100:.2f}%)")
print(f"Pixels de fundo: {color_counts.get(background, 0):,} ({(color_counts.get(background, 0)/(1024*1024))*100:.2f}%)")
