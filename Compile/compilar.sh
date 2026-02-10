pyinstaller --noconfirm --onefile --windowed \
  --add-data "../NEXCore/web:web" \
  --name "NEXCore" \
  --icon "../NEXCore/web/assets/icon.png" \
  ../NEXCore/main.py
read -p "Pressione ENTER para continuar..." < /dev/tty



