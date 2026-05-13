import os
import re
import sqlite3
import config

IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')
_token_re = re.compile(r'[a-z0-9]+')
_trailing_id_re = re.compile(r'-\d+$')

def _stem_plural(token):
    '''Strip simple English plural endings so "Carrots" matches "Carrot".'''
    if len(token) > 4 and token.endswith('ies'):
        return token[:-3] + 'y'  # berries -> berry
    if len(token) > 4 and token.endswith('oes'):
        return token[:-2]        # tomatoes -> tomato, potatoes -> potato
    if len(token) > 3 and token.endswith('s') and not token.endswith('ss'):
        return token[:-1]        # carrots -> carrot, peppers -> pepper
    return token

def _normalize_for_match(name):
    '''Normalize a filename or ingredient name into a sorted, stemmed token
    string for matching. Strips extension and a trailing `-NNN` suffix,
    tokenizes on non-alphanumeric, lowercases, applies simple plural stemming,
    drops pure-digit tokens, and sorts the result so word order doesn't matter.'''
    base = os.path.splitext(name)[0]
    base = _trailing_id_re.sub('', base)
    tokens = _token_re.findall(base.lower())
    tokens = [_stem_plural(t) for t in tokens if not t.isdigit()]
    return ' '.join(sorted(tokens))

# def deleteDB():
#     if os.path.exists('builder.db'):
#         os.remove('builder.db')
#         print('builder.db deleted')
#     else:
#         print('builder.db does not exist')

def initializeDB(includeSampleData=True):
    connection = sqlite3.connect(config.DATABASE)
    cursor = connection.cursor()

    files = ('sql/setup/tables.sql', 'sql/setup/views.sql')
    if includeSampleData:
        files += ('sql/setup/sampledata.sql',)

    for file in files:
        print(f'Executing script {file}')
        sql = config.get_resource(file)
        cursor.executescript(sql)

    connection.commit()
    connection.close()

    print('Database initialized')

def auto_assign_images():
    '''Match files in INGREDIENTS_PATH to ingredients by normalized name.
    Only fills rows where ImageFilename is NULL or empty. A normalized name
    must map to exactly one file to be assigned (ambiguous matches skipped).
    Returns {'assigned': N, 'ambiguous': N, 'unmatched': N}.'''
    counts = {'assigned': 0, 'ambiguous': 0, 'unmatched': 0}
    if not os.path.isdir(config.INGREDIENTS_PATH):
        return counts

    file_index = {}
    for fname in os.listdir(config.INGREDIENTS_PATH):
        if os.path.splitext(fname)[1].lower() not in IMAGE_EXTENSIONS:
            continue
        file_index.setdefault(_normalize_for_match(fname), []).append(fname)

    connection = sqlite3.connect(config.DATABASE)
    cursor = connection.cursor()
    cursor.execute("SELECT Id, Name FROM Ingredients WHERE ImageFilename IS NULL OR ImageFilename = ''")
    for ingredient_id, name in cursor.fetchall():
        matches = file_index.get(_normalize_for_match(name), [])
        if len(matches) == 1:
            cursor.execute('UPDATE Ingredients SET ImageFilename=? WHERE Id=?', (matches[0], ingredient_id))
            counts['assigned'] += 1
        elif len(matches) > 1:
            counts['ambiguous'] += 1
        else:
            counts['unmatched'] += 1

    connection.commit()
    connection.close()
    return counts

def migrateDB():
    '''Idempotently bring an existing database up to the current schema.'''
    connection = sqlite3.connect(config.DATABASE)
    cursor = connection.cursor()

    def column_exists(table, column):
        cursor.execute(f"PRAGMA table_info({table})")
        return any(row[1] == column for row in cursor.fetchall())

    if not column_exists('Ingredients', 'ImageFilename'):
        print('Migrating: adding Ingredients.ImageFilename')
        cursor.execute('ALTER TABLE Ingredients ADD COLUMN ImageFilename TEXT')

    connection.commit()
    connection.close()

if __name__=="__main__":
    initializeDB()