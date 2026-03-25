import os
import shutil
import subprocess
from pathlib import Path

def clean_build_artifacts():
    print("🧹 Cleaning previous build artifacts...")
    paths_to_clean = ["build", "dist"]
    for p in paths_to_clean:
        if os.path.exists(p):
            shutil.rmtree(p)
            print(f"Removed {p}/")

def build_executable():
    print("🚀 Building the executable...")
    # Using the generated spec file ensures we reuse all the hidden-import and path settings
    import sys
    pyinstaller_path = Path(sys.executable).parent / "pyinstaller.exe"
    subprocess.run([str(pyinstaller_path), "GazeAnalyzer.spec", "--noconfirm"], check=True)

if __name__ == "__main__":
    clean_build_artifacts()
    build_executable()
    print("✅ Build complete! You can find the executable in dist/GazeAnalyzer/")
