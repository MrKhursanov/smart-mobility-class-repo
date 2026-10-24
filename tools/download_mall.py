"""Download the original research-only dataset; no Kaggle login is required."""
from pathlib import Path
import hashlib
import urllib.request
ROOT=Path(__file__).resolve().parents[1]
URL='https://staff.ie.cuhk.edu.hk/~ccloy/files/datasets/mall_dataset.zip'
EXPECTED='21baea1066ea1473289c28c2f9fc8440cea3c8d8905b83a66529fbef184d47e3'
p=ROOT/'data/external/mall_dataset.zip'
p.parent.mkdir(parents=True,exist_ok=True)
if not p.exists():
    temp=p.with_suffix('.part')
    with urllib.request.urlopen(URL,timeout=60) as response, temp.open('wb') as output:
        while True:
            chunk=response.read(1024*1024)
            if not chunk:
                break
            output.write(chunk)
    temp.replace(p)
actual=hashlib.sha256(p.read_bytes()).hexdigest()
if actual!=EXPECTED:
    raise RuntimeError('Archive checksum changed; verify the source/version before evaluation')
print(f'Verified {p.stat().st_size} bytes. Research-only terms apply. See docs/DATASET_CARD.md.')
