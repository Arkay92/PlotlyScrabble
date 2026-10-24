"""Prepare this standalone project's code, assets and dictionaries for upload."""
from pathlib import Path
import shutil


def main():
    root = Path(__file__).resolve().parents[1]
    target = root/'deploy'/'plotly-cloud'
    target.mkdir(parents=True,exist_ok=True)
    for name in ('app.py','requirements.txt'):
        shutil.copy2(root/name,target/name)
    for folder in ('wordgame','assets','data/dictionaries','models'):
        destination = target/folder
        destination.mkdir(parents=True,exist_ok=True)
        for source in (root/folder).iterdir():
            if source.is_file():
                shutil.copy2(source,destination/source.name)
    print(f'Upload the contents of {target}')
    print('Keep subfolders. Main file: app.py. Python: 3.11.')


if __name__=='__main__':
    main()
