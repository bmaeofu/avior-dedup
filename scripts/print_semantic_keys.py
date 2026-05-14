import sys, os
sys.path.insert(0, 'src')
from avior_dedup.dedup.normalize import normalize_film_name

folder = 'test-data/dedupe/Dup_test'
if not os.path.exists(folder):
    print('Folder not found:', folder)
    sys.exit(1)

files = sorted(os.listdir(folder))
for f in files:
    key = normalize_film_name(f, [r'terra\\s*x\\-\\s*'], False, False, False)
    print(f'{f} -> {key}')
