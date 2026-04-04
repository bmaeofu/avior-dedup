import argparse
import os
import shutil
import glob
from datetime import datetime
import xml.etree.ElementTree as ET
import re

activitymode = "m"


def move_file(src_path, dest_path, log_file):
    if not os.path.isfile(src_path):
        return False

    if os.path.isfile(dest_path):
        log_file.write(f'{src_path}\t{dest_path}\tDestination already exists\n')
        print(f'Destination already exists: {dest_path}')
        return False

    try:
        if activitymode == "c":
            shutil.copy2(src_path, dest_path)
            log_file.write(f'{src_path}\t{dest_path}\tcopied\n')
        elif activitymode == "m":
            shutil.move(src_path, dest_path)
            log_file.write(f'{src_path}\t{dest_path}\tmoved\n')
        elif activitymode == "d":
            os.remove(src_path)
            log_file.write(f'{src_path}\t\tdeleted\n')
        elif activitymode == "t" or activitymode == "f":
            print(f'test run move_file: {src_path}\t{dest_path}')
            log_file.write(f'{src_path}\t{dest_path}\ttest run\n')
        else:
            shutil.move(src_path, dest_path)
            log_file.write(f'{src_path}\t{dest_path}\tmoved\n')
        return True
    except IOError as e:
        log_file.write(f'{src_path}\t{dest_path}\t{e}\n')
        print(f'Error moving or copying file: {e}')
        return False


def move_files(path, dest_dir, log_file):
    pathonly, filenameonly = os.path.split(path)

    if os.path.abspath(pathonly or '.') == os.path.abspath(dest_dir):
        return

    candidates = [
        ".txt", ".log", ".mp2", ".mp4", ".mkv", ".ts", ".nfo",
        ".mp2.log", ".mpg.log", ".mkv.log", ".plot.txt",
        "-fanart.jpg", "-poster.jpg", "-landscape.jpg", "-thumb.jpg", "-keyart.jpg",
        ".mp4.INFO.log", ".mp2.INFO.log", ".ts.INFO.log", ".mkv.INFO.log",
    ]

    lower_filename = filenameonly.lower()
    lower_candidates = sorted((suffix.lower() for suffix in candidates), key=len, reverse=True)

    nameonly = filenameonly
    for suffix in lower_candidates:
        if lower_filename.endswith(suffix):
            nameonly = filenameonly[:-len(suffix)]
            break
    else:
        nameonly = os.path.splitext(filenameonly)[0]

    # Strip repeated known extensions from the stem (movie.mkv.INFO -> movie)
    stem = nameonly
    while True:
        ext = os.path.splitext(stem)[1].lower()
        if ext in ('.info', '.mkv', '.ts', '.mpg', '.mp2', '.nfo'):
            stem = os.path.splitext(stem)[0]
        else:
            break
    nameonly = stem

    if activitymode == "c":
        print(f'copying files: {nameonly} -> {dest_dir}')
    elif activitymode == "m":
        print(f'moving files: {nameonly} -> {dest_dir}')
    elif activitymode == "d":
        print(f'deleting files: {nameonly} -> {dest_dir}')
    elif activitymode == "t" or activitymode == "f":
        print(f'test run files: {nameonly} -> {dest_dir}')
    else:
        print(f'moving files: {nameonly} -> {dest_dir}')

    search_dir = pathonly if pathonly else '.'
    lower_name = nameonly.lower()

    try:
        with os.scandir(search_dir) as it:
            for entry in it:
                if not entry.is_file():
                    continue

                ename_low = entry.name.lower()

                # HIER die exakte Logik:
                for suf in lower_candidates:
                    if ename_low == lower_name + suf:
                        dest = os.path.join(dest_dir, entry.name)
                        move_file(entry.path, dest, log_file)
                        break
    except OSError as e:
        print(f'Error scanning directory {search_dir}: {e}')

def match_and_or_(groups, match_func):
    """
    Gibt den ersten passenden Suchterm zurück,
    sonst None.
    """
    for group in groups:              # OR
        for and_group in group:       # OR innerhalb
            if all(match_func(t) for t in and_group):  # AND
                return and_group      # <-- das ist der Match
    return None

def search_file(path, dest_dir, search_groups, outfile, log_file):
    if not os.path.isfile(path):
        #print(f'searching path: {path}')
        return
    try:
        with open(path, 'r', encoding="utf8", errors="surrogateescape") as f:
            contents = f.read()

#        def match_func(s):
#            return s.lower() in contents.lower()

        def match_val_func(s):
            term = s.strip()
            if not term:
                return None
            pattern = re.escape(term)
            m = re.search(pattern, contents, flags=re.IGNORECASE)
            return m.group(0) if m else None

        # Prüfe jede OR-Gruppe
        for group in search_groups:      # OR
            for and_group in group:      # AND
                values = [match_val_func(term) for term in and_group]
                if all(v is not None for v in values):
                    # Match gefunden → Ausgabe
                    match_str = " & ".join(and_group)
                    found_str = " | ".join(values)
                    print(f"MATCH FOUND: {path}  -->  {match_str}  [Found: {found_str}]")
                    outfile.write(path + "\t" + match_str + "\t" + found_str + "\n")
                    move_files(path, dest_dir, log_file)
                    return   # nur erster Treffer pro Datei

    except IOError as e:
        print("cannot access", path, e, sep='\t')

def _parse_condition(condition_str):
    # returns a predicate fn(value: float) -> bool or None if cannot parse
    s = (condition_str or '').strip()
    if not s:
        return None
    # find operator-number pairs like >4, <=5.5, ==6
    parts = re.findall(r'([<>]=?|==)\s*([0-9]+(?:\.[0-9]+)?)', s)
    if parts:
        conds = []
        for op, num in parts:
            n = float(num)
            if op == '>':
                conds.append(lambda v, n=n: v > n)
            elif op == '>=':
                conds.append(lambda v, n=n: v >= n)
            elif op == '<':
                conds.append(lambda v, n=n: v < n)
            elif op == '<=':
                conds.append(lambda v, n=n: v <= n)
            elif op == '==':
                conds.append(lambda v, n=n: v == n)
        return lambda v: all(c(v) for c in conds)
    # range like 4-6 or 4..6 or 4<6 (with number-number)
    m = re.match(r'^\s*([0-9]+(?:\.[0-9]+)?)\s*[-–—\.]{1,2}\s*([0-9]+(?:\.[0-9]+)?)\s*$', s)
    if m:
        lo = float(m.group(1)); hi = float(m.group(2))
        return lambda v: lo <= v <= hi
    # fallback single number equals
    m = re.match(r'^\s*([0-9]+(?:\.[0-9]+)?)\s*$', s)
    if m:
        n = float(m.group(1))
        return lambda v: v == n
    return None

def search_xmlfile(path, dest_dir, search_groups, outfile, log_file):
    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except (ET.ParseError, IOError) as e:
        print(f'XML parse error for {path}: {e}')
        return

    # Sammle Ratings
    ratings = []
    for rating_elem in root.findall('.//ratings/rating'):
        name = (rating_elem.get('name') or '').strip().lower()
        value_text = rating_elem.findtext('value') or ''
        votes_text = rating_elem.findtext('votes') or ''
        try:
            value = float(value_text) if value_text.strip() != '' else None
        except ValueError:
            value = None
        try:
            votes = int(votes_text) if votes_text.strip() != '' else 0
        except ValueError:
            votes = 0
        if value is not None:
            ratings.append({'name': name, 'value': value, 'votes': votes})

    # Bewertung auswählen
    selected_value = None
    if ratings:
        imdb = next((r for r in ratings if r['name'] == 'imdb'), None)
        if imdb and imdb['votes'] >= 10:
            selected_value = imdb['value']
        else:
            ratings_sorted = sorted(ratings, key=lambda r: r['votes'], reverse=True)
            selected_value = ratings_sorted[0]['value']

    # Fallback <userrating>
    if selected_value is None:
        userrating_text = root.findtext('.//userrating') or ''
        try:
            selected_value = float(userrating_text) if userrating_text.strip() != '' else None
        except ValueError:
            selected_value = None

    # ---- AND/OR matching ----
    def xml_match(search_string):
        try:
            tag, attrib = search_string.strip().split(':', 1)
        except ValueError:
            return None

        tag = tag.strip().lower()
        attrib = attrib.strip().lower()

        if tag == 'rating':
            pred = _parse_condition(attrib)
            if pred and (selected_value is not None) and pred(selected_value):
                return str(selected_value)
            return None
        else:
            tag_nodes = root.findall(tag)

            # Numeric comparisons for generic XML tags, e.g. plot_sim_score:>0.9
            # (rating keeps its dedicated selection logic above).
            pred = _parse_condition(attrib)
            if pred:
                for tagf in tag_nodes:
                    txt = (tagf.text or '').strip()
                    if txt == '':
                        continue
                    try:
                        value = float(txt)
                    except ValueError:
                        continue
                    if pred(value):
                        return txt
                return None

            # Existenz-Pruefung fuer XML-Tags
            # tag:exists   -> mindestens ein Tag vorhanden (unabhaengig vom Inhalt)
            # tag:!exists  -> kein Tag vorhanden
            if attrib == 'exists':
                return 'exists' if tag_nodes else None
            if attrib == '!exists':
                return '!exists' if not tag_nodes else None

            # Wildcard-Unterstützung: *, *text, text*, *text*
            has_wildcard_start = attrib.startswith('*')
            has_wildcard_end = attrib.endswith('*')
            
            if has_wildcard_start or has_wildcard_end:
                # Entferne Wildcards für den Vergleich
                search_term = attrib.strip('*')
                
                for tagf in tag_nodes:
                    txt = (tagf.text or '').strip()
                    txt_lower = txt.lower()
                    
                    if has_wildcard_start and has_wildcard_end:
                        # *text* → contains
                        if search_term in txt_lower:
                            return txt
                    elif has_wildcard_start:
                        # *text → endswith
                        if txt_lower.endswith(search_term):
                            return txt
                    elif has_wildcard_end:
                        # text* → startswith
                        if txt_lower.startswith(search_term):
                            return txt
            else:
                # Keine Wildcards → exakte Übereinstimmung (wie bisher)
                for tagf in tag_nodes:
                    txt = (tagf.text or '').strip()
                    if txt.lower() == attrib:
                        return txt
        return None

    # Prüfe jede OR-Gruppe
    for group in search_groups:   # OR
        for and_group in group:   # AND
            values = [xml_match(term) for term in and_group]
            if all(v is not None for v in values):
                # Match gefunden → Ausgabe auf Bildschirm
                match_str = " & ".join(and_group)
                found_str = " | ".join(values)
                print(f"MATCH FOUND: {path}  -->  {match_str}  [Found: {found_str}]")
                outfile.write(path + "\t" + match_str + "\t" + found_str + "\n")
                move_files(path, dest_dir, log_file)
                return   # nur erster Treffer pro Datei


def search_path(path, dest_dir, extensions, search_groups, output_path, recursive=False):
    os.makedirs(dest_dir, exist_ok=True)
    log_path = os.path.join(dest_dir, 'log.txt')
    header = 'Datum: ' + datetime.now().strftime('%y-%m-%d %H:%M:%S') + '\n'

    try:
        with open(output_path, 'a', encoding='utf-8') as outfile, \
             open(log_path, 'a', encoding='utf-8') as log_file:

            outfile.write(header)
            log_file.write(header)

            if os.path.isfile(path):
                ext = os.path.splitext(path)[1]
                if extensions and ext in extensions:
                    if ext == '.nfo':
                        #print(f'searching file: {path}')
                        search_xmlfile(path, dest_dir, search_groups, outfile, log_file)
                    else:
                        #print(f'searching file: {path}')
                        search_file(path, dest_dir, search_groups, outfile, log_file)
            else:
                if recursive:
                    for root, _, files in os.walk(path):
                        print(f'Entering directory: {root}')
                        for filename in files:
                            full = os.path.join(root, filename)
                            ext = os.path.splitext(filename)[1]
                            if extensions and ext in extensions:
                                if ext == '.nfo':
                                    #print(f'searching file: {full}')
                                    search_xmlfile(full, dest_dir, search_groups, outfile, log_file)
                                else:
                                    #print(f'searching file: {full}')
                                    search_file(full, dest_dir, search_groups, outfile, log_file)
                else:
                    print(f'Entering directory: {path}')
                    with os.scandir(path) as entries:
                        for entry in entries:
                            if not entry.is_file():
                                continue

                            ext = os.path.splitext(entry.name)[1]
                            if extensions and ext in extensions:
                                if ext == '.nfo':
                                    search_xmlfile(entry.path, dest_dir, search_groups, outfile, log_file)
                                else:
                                    search_file(entry.path, dest_dir, search_groups, outfile, log_file)

    except IOError as e:
        print(f'Error opening output/log file: {e}')


def parse_search_expression(expr_list):
    """
    Parse boolean search expressions.

    Input (from CLI):
        ["a&b|c", "d&e"]

    Means:
        (a AND b) OR (c)
        (d AND e)

    Output structure:
        [
          [ ['a','b'], ['c'] ],
          [ ['d','e'] ]
        ]

    => OR of AND-groups
    """
    groups = []
    for expr in expr_list or []:
        expr = (expr or '').strip()
        if not expr:
            continue
        or_parts = expr.split('|')
        group = []
        for part in or_parts:
            and_parts = [p.strip() for p in part.split('&') if p.strip()]
            if and_parts:
                group.append(and_parts)
        if group:
            groups.append(group)
    return groups


def main():
    parser = argparse.ArgumentParser(
        description=
        'Search a directory for files with certain extensions.\n'
        'Use --recursive to include subdirectories.\n'
        'Search expressions support boolean logic:\n'
        '  &  = AND  (all terms must match)\n'
        '  |  = OR   (any group may match)\n'
        '\n'
        'Examples:\n'
        '  "action&thriller"\n'
        '  "action&thriller|comedy"\n'
        '  "rating:>7&year:2020|rating:>8"\n'
    )

    parser.add_argument(
        'activitymode',
        help=
        'Action mode:\n'
        '  c = copy matching files\n'
        '  m = move matching files\n'
        '  d = delete matching files\n'
        '  t or f = test run (no changes)'
    )

    parser.add_argument(
        'source_dir',
        help='Path to the directory or single file to search'
    )

    parser.add_argument(
        'dest_dir',
        help='Destination directory for moved/copied files'
    )

    parser.add_argument(
        '--extensions', '-e',
        type=str,
        nargs='+',
        help=
        'File extensions to search for.\n'
        'Examples: .txt .nfo .log'
    )

    parser.add_argument(
        '--search_strings', '-s',
        nargs='+',
        help=
        'Search expressions with boolean logic.\n'
        '\n'
        'Operators:\n'
        '  &  AND   all conditions must match\n'
        '  |  OR    any group may match\n'
        '\n'
        'Text files:\n'
        '  "action&thriller"\n'
        '  "action|thriller|comedy"\n'
        '\n'
        'XML (.nfo):\n'
        '  "genre:Action&year:2020"\n'
        '  "rating:>7&year:2020|rating:>8"\n'
        '\n'
        'Wildcards (nur XML):\n'
        '  genre:Action        → exakte Übereinstimmung\n'
        '  genre:*Action*      → enthält "Action"\n'
        '  genre:Action*       → beginnt mit "Action"\n'
        '  genre:*Action       → endet mit "Action"\n'
        '\n'
        'XML-Existenzpruefung:\n'
        '  nfo_status:exists   → Tag ist vorhanden\n'
        '  nfo_status:!exists  → Tag ist nicht vorhanden\n'
        '\n'
        'Rating conditions:\n'
        '  rating:>7\n'
        '  rating:>4<6\n'
        '  rating:4-6\n'
        ' & hat Priorität vor |\n'
        ' Klammern werden nicht unterstützt.\n'
    )

    parser.add_argument(
        '--output_file', '-o',
        default='result.txt',
        help='File to write the result list to (default: result.txt)'
    )

    parser.add_argument(
        '--recursive', '-r',
        action='store_true',
        help='Search subdirectories recursively'
    )

    args = parser.parse_args()

    global activitymode
    activitymode = args.activitymode

    # parse AND/OR expressions
    search_groups = parse_search_expression(args.search_strings)

    search_path(
        args.source_dir,
        args.dest_dir,
        args.extensions,
        search_groups,
        args.output_file,
        recursive=args.recursive
    )

if __name__ == '__main__':
    main()
