# streamlit_app.py
# Este arquivo serve como "ponte" para o Streamlit Cloud encontrar o dashboard.py

import subprocess
import sys

# Executa o dashboard.py como se fosse o app principal
if __name__ == "__main__":
    # Caminho relativo para garantir que funcione no cloud
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    target_script = os.path.join(current_env, "dashboard.py")
    
    # Simplesmente importa e roda o script
    exec(open(target_script).read())