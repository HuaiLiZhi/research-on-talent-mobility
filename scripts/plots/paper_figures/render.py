"""Render one canonical figure using the maintained manuscript manifest."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("figure", choices=[f"Fig{i}" for i in range(1, 7)])
    args = parser.parse_args()
    manifest = json.loads(Path(__file__).with_name("manifest.json").read_text(encoding="utf-8"))
    figure = next(item for item in manifest["figures"] if item["manuscript_figure"] == args.figure)
    env = os.environ.copy()
    directories = [ROOT, ROOT / "figures/v3", ROOT / "figures/v4", ROOT / "scripts/reports",
                   ROOT / "scripts/plots/paper_figures/qa"]
    env["PYTHONPATH"] = os.pathsep.join(map(str, directories)) + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run([sys.executable, str(ROOT / figure["renderer"])], cwd=ROOT, env=env, check=True)

if __name__ == "__main__":
    main()
