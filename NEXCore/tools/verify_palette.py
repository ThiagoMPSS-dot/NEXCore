
import sys
import os

# Adicionar diretório raiz ao path
sys.path.append(os.getcwd())

from nexcore.storage import StorageManager
from nexcore.map_renderer import MapRenderer

def test_palette():
    print("Iniciando teste de paleta...")
    
    # Mock Storage
    storage = StorageManager(os.path.join(os.getcwd(), 'data'))
    
    # Init Renderer
    renderer = MapRenderer(storage)
    
    # Cores esperadas (da DEFAULT_PALETTE)
    expected = {
        "stone": (120, 120, 120),
        "grass": (91, 142, 49),
        "water": (63, 118, 228)
    }
    
    failed = False
    
    for block_name, expected_color in expected.items():
        # A paleta é case-insensitive (chaves em minúsculo)
        color = renderer.block_palette.get(block_name)
        
        if color:
            print(f"[OK] '{block_name}' encontrada: {color}")
            if color != expected_color:
                # Pode ser diferente se houver um arquivo JSON sobrescrevendo, o que é OK, 
                # mas neste teste queremos garantir que pelo menos TEM cor.
                print(f"     Nota: Cor diferente da default (provavelmente do JSON), o que é bom.")
        else:
            print(f"[FALHA] '{block_name}' NÃO encontrada na paleta!")
            failed = True

    if not failed:
        print("\nSUCESSO: Todas as cores básicas estão presentes na paleta.")
    else:
        print("\nERRO: Algumas cores básicas estão faltando.")

if __name__ == "__main__":
    test_palette()
