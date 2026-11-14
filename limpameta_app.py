"""Ponto de entrada para rodar do código-fonte e para o PyInstaller."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from limpameta.ui import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
