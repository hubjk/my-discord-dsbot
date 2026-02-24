import re

path = '/home/infaos/Документи/dsbot/main.py'
with open(path, encoding='utf-8') as f:
    c = f.read()

new_cyrmap = """    # Таблиця: Кирилиця -> Латиниця (QWERTY Ukrainian layout)
    CYRMAP = str.maketrans({
        'й':'q','ц':'w','у':'e','к':'r','е':'t','н':'y','г':'u','ш':'i','щ':'o','з':'p',
        'ф':'a','і':'s','в':'d','а':'f','п':'g','р':'h','о':'j','л':'k','д':'l',
        'я':'z','ч':'x','с':'c','м':'v','и':'b','т':'n','ь':'m',
        'Й':'Q','Ц':'W','У':'E','К':'R','Е':'T','Н':'Y','Г':'U','Ш':'I','Щ':'O','З':'P',
        'Ф':'A','І':'S','В':'D','А':'F','П':'G','Р':'H','О':'J','Л':'K','Д':'L',
        'Я':'Z','Ч':'X','С':'C','М':'V','И':'B','Т':'N','Ь':'M',
    })"""

c2 = re.sub(
    r'    # Таблиця відповідності.*?    \)',
    new_cyrmap,
    c,
    flags=re.DOTALL
)

if c2 != c:
    with open(path, 'w', encoding='utf-8') as f:
        f.write(c2)
    print('Replaced OK')
else:
    print('No match found!')
    # Debug: show the relevant lines
    for i, line in enumerate(c.split('\n')[93:107], 94):
        print(f"{i}: {repr(line)}")
