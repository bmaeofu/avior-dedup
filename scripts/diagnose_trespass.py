import sys, os
sys.path.insert(0, 'src')
from avior_dedup.dedup.suffix import match_suffix
from avior_dedup import config

folder = 'test-data/dedupe/Dup_test'
if not os.path.isdir(folder):
    print('Folder not found:', folder)
    sys.exit(1)

files = sorted(os.listdir(folder))
for f in files:
    if 'Trespass' in f:
        base, suf = match_suffix(f)
        print('FILE:', f)
        print('  base ->', repr(base))
        print('  suffix ->', repr(suf))
        for ext in config.video_suffixes():
            exists = os.path.exists(os.path.join(folder, base + ext))
            print(f'    video {ext}:', exists)
        print()
