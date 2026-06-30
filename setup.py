from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
VENV_DIR = BASE_DIR / ".venv"
REQUIREMENTS_FILE = BASE_DIR / "requirements.txt"
APP_FILE = BASE_DIR / "app.py"


def run_command(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=BASE_DIR, check=check)


def get_venv_python() -> Path:
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def venv_looks_healthy(venv_python: Path) -> bool:
    if not venv_python.exists():
        return False
    try:
        result = subprocess.run(
            [str(venv_python), "-c", "print('ok')"],
            cwd=BASE_DIR,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return result.returncode == 0


def recreate_venv() -> Path:
    if VENV_DIR.exists():
        print("Ambiente virtual quebrado detectado. Recriando .venv...")
        shutil.rmtree(VENV_DIR)
    print("Criando ambiente virtual em .venv...")
    run_command([sys.executable, "-m", "venv", str(VENV_DIR)])
    venv_python = get_venv_python()
    if not venv_python.exists():
        raise RuntimeError("Não foi possível criar o ambiente virtual.")
    return venv_python


def ensure_venv() -> Path:
    venv_python = get_venv_python()
    if venv_looks_healthy(venv_python):
        return venv_python
    return recreate_venv()


def ensure_dependencies(venv_python: Path) -> None:
    if not REQUIREMENTS_FILE.exists():
        raise FileNotFoundError("requirements.txt não encontrado.")

    print("Instalando/atualizando dependências...")
    run_command([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"])
    run_command([str(venv_python), "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)])


def ensure_database(venv_python: Path) -> None:
    if not APP_FILE.exists():
        raise FileNotFoundError("app.py não encontrado.")

    print("Validando banco de dados...")
    run_command([str(venv_python), "-c", "import app; print('Banco pronto.')"])


def run_project(venv_python: Path) -> None:
    print("Iniciando o projeto...")
    raise SystemExit(run_command([str(venv_python), str(APP_FILE)], check=False).returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepara o projeto para execução.")
    parser.add_argument("--run", action="store_true", help="Inicia o projeto após preparar o ambiente.")
    args = parser.parse_args()

    venv_python = ensure_venv()
    ensure_dependencies(venv_python)
    ensure_database(venv_python)

    if args.run:
        run_project(venv_python)
    else:
        print("Projeto preparado com sucesso. Para iniciar, execute: .venv\\Scripts\\python.exe app.py")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
