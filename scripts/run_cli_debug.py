import sys, traceback

sys.argv = ['cli.py', 'f', 'test-data/dedupe/Dup_test', 'out/dedupe_test', 'dedup_log.txt', '--duptype', 'semantic']

try:
    from avior_dedup.cli import main
    main()
except Exception:
    traceback.print_exc()
