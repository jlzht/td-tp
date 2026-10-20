"""Caminhos padrão do projeto, relativos à raiz do repositório."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_FILE = PROJECT_ROOT / "dados" / "dados_exemplo.json"
CONFIG_DIR = PROJECT_ROOT / "configuracoes"
RESULTS_DIR = PROJECT_ROOT / "resultados"
