#!/usr/bin/env python3
"""Перший прохід нормалізації українського тексту для озвучення (TTS).

Розгортає в слова: числа, дробові числа, відсотки, одиниці виміру,
діапазони, дати, роки, століття, час, артеріальний тиск, телефони,
номери, порядкові числівники з нарощенням ("5-й"), типові скорочення.
Перетворює markdown (заголовки, списки, таблиці, посилання) на суцільну
мовлену прозу.

Скрипт не розв'язує всі відмінкові узгодження — він дає детерміновану
основу, яку потім вичитують за правилами SKILL.md. Параметр --report
виводить у stderr місця, що потребують ручної перевірки.

Використання:
    python3 normalize_uk.py input.md > output.txt
    cat text.txt | python3 normalize_uk.py - --report
    python3 normalize_uk.py --selftest
"""

import argparse
import re
import sys

# ---------------------------------------------------------------------------
# Кількісні числівники
# ---------------------------------------------------------------------------

UNITS = {
    'm': ['нуль', 'один', 'два', 'три', 'чотири', "п'ять", 'шість', 'сім',
          'вісім', "дев'ять"],
    'f': ['нуль', 'одна', 'дві', 'три', 'чотири', "п'ять", 'шість', 'сім',
          'вісім', "дев'ять"],
    'n': ['нуль', 'одне', 'два', 'три', 'чотири', "п'ять", 'шість', 'сім',
          'вісім', "дев'ять"],
}
UNITS_GEN = {
    'm': ['нуля', 'одного', 'двох', 'трьох', 'чотирьох', "п'яти", 'шести',
          'семи', 'восьми', "дев'яти"],
}
UNITS_GEN['n'] = UNITS_GEN['m']
UNITS_GEN['f'] = ['нуля', 'однієї'] + UNITS_GEN['m'][2:]

TEENS = ['десять', 'одинадцять', 'дванадцять', 'тринадцять', 'чотирнадцять',
         "п'ятнадцять", 'шістнадцять', 'сімнадцять', 'вісімнадцять',
         "дев'ятнадцять"]
TEENS_GEN = [w[:-1] + 'и' for w in TEENS]          # десяти, одинадцяти...
TENS = ['', '', 'двадцять', 'тридцять', 'сорок', "п'ятдесят", 'шістдесят',
        'сімдесят', 'вісімдесят', "дев'яносто"]
TENS_GEN = ['', '', 'двадцяти', 'тридцяти', 'сорока', "п'ятдесяти",
            'шістдесяти', 'сімдесяти', 'вісімдесяти', "дев'яноста"]
HUNDREDS = ['', 'сто', 'двісті', 'триста', 'чотириста', "п'ятсот", 'шістсот',
            'сімсот', 'вісімсот', "дев'ятсот"]
HUNDREDS_GEN = ['', 'ста', 'двохсот', 'трьохсот', 'чотирьохсот', "п'ятисот",
                'шестисот', 'семисот', 'восьмисот', "дев'ятисот"]

# (значення, рід, форми Н.в. (1, 2-4, 5+), форми Р.в. (1, інші))
SCALES = [
    (10 ** 9, 'm', ('мільярд', 'мільярди', 'мільярдів'), ('мільярда', 'мільярдів')),
    (10 ** 6, 'm', ('мільйон', 'мільйони', 'мільйонів'), ('мільйона', 'мільйонів')),
    (10 ** 3, 'f', ('тисяча', 'тисячі', 'тисяч'), ('тисячі', 'тисяч')),
]


def plural(n, forms):
    """Обирає форму іменника за числом: (один, два-чотири, п'ять+)."""
    n = abs(n) % 100
    if 11 <= n <= 14:
        return forms[2]
    r = n % 10
    if r == 1:
        return forms[0]
    if 2 <= r <= 4:
        return forms[1]
    return forms[2]


def _is_one(n):
    return n % 10 == 1 and n % 100 != 11


def _triad(n, gender, case):
    gen = case == 'gen'
    words = []
    h, rest = divmod(n, 100)
    if h:
        words.append((HUNDREDS_GEN if gen else HUNDREDS)[h])
    if 10 <= rest <= 19:
        words.append((TEENS_GEN if gen else TEENS)[rest - 10])
    else:
        t, u = divmod(rest, 10)
        if t:
            words.append((TENS_GEN if gen else TENS)[t])
        if u:
            words.append((UNITS_GEN if gen else UNITS)[gender][u])
    return words


def cardinal(n, gender='m', case='nom'):
    """Кількісний числівник: рід m/f/n, відмінок nom/gen."""
    if n == 0:
        return 'нуля' if case == 'gen' else 'нуль'
    words = ['мінус'] if n < 0 else []
    n = abs(n)
    for value, g, nom_forms, gen_forms in SCALES:
        q, n = divmod(n, value)
        if not q:
            continue
        if q != 1:  # «тисяча», «мільйон» без «одна/один»
            words += cardinal(q, g, case).split()
        if case == 'gen':
            words.append(gen_forms[0] if _is_one(q) else gen_forms[1])
        else:
            words.append(plural(q, nom_forms))
    if n:
        words += _triad(n, gender, case)
    return ' '.join(words)


# ---------------------------------------------------------------------------
# Порядкові числівники
# ---------------------------------------------------------------------------

ORD_UNITS = ['нульов', 'перш', 'друг', 'трет', 'четверт', "п'ят", 'шост',
             'сьом', 'восьм', "дев'ят"]
ORD_TEENS = [w[:-1] for w in TEENS]                 # десят, одинадцят...
ORD_TENS = ['', '', 'двадцят', 'тридцят', 'сороков', "п'ятдесят",
            'шістдесят', 'сімдесят', 'вісімдесят', "дев'яност"]
ORD_HUNDREDS = ['', 'сот', 'двохсот', 'трьохсот', 'чотирьохсот', "п'ятисот",
                'шестисот', 'семисот', 'восьмисот', "дев'ятисот"]

HARD = {'m_nom': 'ий', 'm_gen': 'ого', 'm_loc': 'ому',
        'f_nom': 'а', 'f_gen': 'ої', 'f_loc': 'ій',
        'n_nom': 'е', 'n_gen': 'ого', 'n_loc': 'ому', 'pl_nom': 'і', 'pl_gen': 'их'}
SOFT = {'m_nom': 'ій', 'm_gen': 'ього', 'm_loc': 'ьому',
        'f_nom': 'я', 'f_gen': 'ьої', 'f_loc': 'ій',
        'n_nom': 'є', 'n_gen': 'ього', 'n_loc': 'ьому', 'pl_nom': 'і', 'pl_gen': 'іх'}


def ordinal(n, form='m_nom'):
    """Порядковий числівник. form: m_nom, m_gen, m_loc, f_*, n_*, pl_gen."""
    if n >= 1000 and n % 1000 == 0 and n < 10 ** 6:
        q = n // 1000
        prefix = '' if q == 1 else cardinal(q, 'f', 'gen').replace(' ', '')
        prefix = prefix.replace('однієї', 'одно')
        return prefix + 'тисячн' + HARD[form]
    rest = n % 100
    h = (n % 1000) // 100
    if rest == 0:
        stem, base = ORD_HUNDREDS[h], n - h * 100
    elif rest < 10:
        stem, base = ORD_UNITS[rest], n - rest
    elif rest < 20:
        stem, base = ORD_TEENS[rest - 10], n - rest
    else:
        t, u = divmod(rest, 10)
        if u == 0:
            stem, base = ORD_TENS[t], n - rest
        else:
            stem, base = ORD_UNITS[u], n - u
    ending = (SOFT if stem == 'трет' else HARD)[form]
    prefix = cardinal(base) + ' ' if base else ''
    return prefix + stem + ending


# ---------------------------------------------------------------------------
# Дробові числа
# ---------------------------------------------------------------------------

FRAC_NAMES = {1: 'десят', 2: 'сот', 3: 'тисячн', 4: 'десятитисячн',
              5: 'стотисячн', 6: 'мільйонн'}


def decimal(int_part, frac_digits, case='nom'):
    """3,5 -> «три цілих п'ять десятих» (Н.в.) / «трьох цілих п'яти десятих» (Р.в.)."""
    if len(frac_digits) not in FRAC_NAMES:
        digits = ' '.join(UNITS['m'][int(d)] for d in frac_digits)
        return f'{cardinal(int_part, "f", case)} кома {digits}'
    gen = case == 'gen'
    frac = int(frac_digits)
    whole = cardinal(int_part, 'f', case) + ' ' + (
        ('цілої' if gen else 'ціла') if _is_one(int_part) else 'цілих')
    stem = FRAC_NAMES[len(frac_digits)]
    part = cardinal(frac, 'f', case) + ' ' + stem + (
        ('ої' if gen else 'а') if _is_one(frac) else 'их')
    return whole + ' ' + part


# ---------------------------------------------------------------------------
# Одиниці виміру: (одн., 2-4, 5+, Р.в. однини — після дробу), рід
# ---------------------------------------------------------------------------

def _u(one, few, many, gen_sg, gender='m'):
    return (one, few, many, gen_sg), gender


UNIT_TABLE = {
    '%': _u('відсоток', 'відсотки', 'відсотків', 'відсотка'),
    '‰': _u('проміле', 'проміле', 'проміле', 'проміле', 'n'),
    '°C': _u('градус Цельсія', 'градуси Цельсія', 'градусів Цельсія', 'градуса Цельсія'),
    '℃': _u('градус Цельсія', 'градуси Цельсія', 'градусів Цельсія', 'градуса Цельсія'),
    '°': _u('градус', 'градуси', 'градусів', 'градуса'),
    'мм рт. ст.': _u('міліметр ртутного стовпа', 'міліметри ртутного стовпа',
                     'міліметрів ртутного стовпа', 'міліметра ртутного стовпа'),
    'мм рт.ст.': _u('міліметр ртутного стовпа', 'міліметри ртутного стовпа',
                    'міліметрів ртутного стовпа', 'міліметра ртутного стовпа'),
    'уд/хв': _u('удар за хвилину', 'удари за хвилину', 'ударів за хвилину', 'удару за хвилину'),
    'уд./хв': _u('удар за хвилину', 'удари за хвилину', 'ударів за хвилину', 'удару за хвилину'),
    'мг/кг': _u('міліграм на кілограм', 'міліграми на кілограм',
                'міліграмів на кілограм', 'міліграма на кілограм'),
    'мл/год': _u('мілілітр на годину', 'мілілітри на годину',
                 'мілілітрів на годину', 'мілілітра на годину'),
    'км/год': _u('кілометр на годину', 'кілометри на годину',
                 'кілометрів на годину', 'кілометра на годину'),
    'ммоль/л': _u('мілімоль на літр', 'мілімолі на літр',
                  'мілімолів на літр', 'мілімоля на літр'),
    'м/с': _u('метр за секунду', 'метри за секунду', 'метрів за секунду', 'метра за секунду'),
    'км': _u('кілометр', 'кілометри', 'кілометрів', 'кілометра'),
    'м': _u('метр', 'метри', 'метрів', 'метра'),
    'см': _u('сантиметр', 'сантиметри', 'сантиметрів', 'сантиметра'),
    'мм': _u('міліметр', 'міліметри', 'міліметрів', 'міліметра'),
    'кг': _u('кілограм', 'кілограми', 'кілограмів', 'кілограма'),
    'г': _u('грам', 'грами', 'грамів', 'грама'),
    'мг': _u('міліграм', 'міліграми', 'міліграмів', 'міліграма'),
    'мкг': _u('мікрограм', 'мікрограми', 'мікрограмів', 'мікрограма'),
    'т': _u('тонна', 'тонни', 'тонн', 'тонни', 'f'),
    'л': _u('літр', 'літри', 'літрів', 'літра'),
    'мл': _u('мілілітр', 'мілілітри', 'мілілітрів', 'мілілітра'),
    'га': _u('гектар', 'гектари', 'гектарів', 'гектара'),
    'год': _u('година', 'години', 'годин', 'години', 'f'),
    'хв': _u('хвилина', 'хвилини', 'хвилин', 'хвилини', 'f'),
    'сек': _u('секунда', 'секунди', 'секунд', 'секунди', 'f'),
    'с': _u('секунда', 'секунди', 'секунд', 'секунди', 'f'),
    'грн': _u('гривня', 'гривні', 'гривень', 'гривні', 'f'),
    '$': _u('долар', 'долари', 'доларів', 'долара'),
    '€': _u('євро', 'євро', 'євро', 'євро', 'n'),
    'шт.': _u('штука', 'штуки', 'штук', 'штуки', 'f'),
    'од.': _u('одиниця', 'одиниці', 'одиниць', 'одиниці', 'f'),
    'тис.': _u('тисяча', 'тисячі', 'тисяч', 'тисячі', 'f'),
    'млн': _u('мільйон', 'мільйони', 'мільйонів', 'мільйона'),
    'млрд': _u('мільярд', 'мільярди', 'мільярдів', 'мільярда'),
}
_UNIT_KEYS = sorted(UNIT_TABLE, key=len, reverse=True)
UNIT_RE = '|'.join(re.escape(k) for k in _UNIT_KEYS)
# Після одиниці не повинна йти літера (щоб «м» не з'їдало «метро»).
UNIT_END = r'(?![А-Яа-яІіЇїЄєҐґA-Za-z])'

NUM = r'(\d{1,3}(?:[   ]\d{3})+|\d+)(?:[,.](\d+)(?![.,]\d))?'

MONTHS_GEN = ['', 'січня', 'лютого', 'березня', 'квітня', 'травня', 'червня',
              'липня', 'серпня', 'вересня', 'жовтня', 'листопада', 'грудня']
MONTH_WORDS = '|'.join(MONTHS_GEN[1:])


def _int(s):
    return int(re.sub(r'\D', '', s))


def number_words(int_s, frac_s, gender='m', case='nom'):
    if frac_s:
        return decimal(_int(int_s), frac_s, case)
    return cardinal(_int(int_s), gender, case)


def with_unit(int_s, frac_s, unit_key):
    forms, gender = UNIT_TABLE[unit_key]
    if frac_s:
        return f'{decimal(_int(int_s), frac_s)} {forms[3]}'
    n = _int(int_s)
    return f'{cardinal(n, gender)} {plural(n, forms[:3])}'


def roman_to_int(s):
    vals = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100}
    total = 0
    for a, b in zip(s, s[1:] + ' '):
        v = vals[a]
        total += -v if b != ' ' and vals.get(b, 0) > v else v
    return total


# ---------------------------------------------------------------------------
# Markdown і таблиці
# ---------------------------------------------------------------------------

def _cells(line):
    return [c.strip() for c in line.strip().strip('|').split('|')]


def table_to_speech(lines):
    header = _cells(lines[0])
    body = [_cells(l) for l in lines[2:]]
    out = [f'Таблиця. Стовпці: {", ".join(h for h in header if h)}.']
    for row in body:
        if not any(row):
            continue
        parts = []
        for h, c in zip(header[1:], row[1:]):
            if c in ('', '-', '—', '–'):
                c = 'немає даних'
            parts.append(f'{h} — {c}' if h else c)
        lead = row[0] or 'Рядок'
        out.append(f'{lead}: {"; ".join(parts)}.' if parts else f'{lead}.')
    out.append('Кінець таблиці.')
    return '\n'.join(out)


def markdown_to_prose(text):
    text = re.sub(r'```.*?```', ' (тут у тексті фрагмент коду) ', text, flags=re.S)
    lines = text.split('\n')
    result, i = [], 0
    is_sep = re.compile(r'^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$')
    while i < len(lines):
        line = lines[i]
        if (line.strip().startswith('|') and i + 1 < len(lines)
                and is_sep.match(lines[i + 1])):
            block = [line, lines[i + 1]]
            i += 2
            while i < len(lines) and lines[i].strip().startswith('|'):
                block.append(lines[i])
                i += 1
            result.append(table_to_speech(block))
            continue
        result.append(line)
        i += 1
    text = '\n'.join(result)

    text = re.sub(r'!\[([^\]]*)\]\([^)]*\)', r'\1', text)            # зображення
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)              # посилання
    text = re.sub(r'https?://(?:www\.)?([^/\s)]+)\S*', r'посилання на сайт \1', text)
    text = re.sub(r'^\s*([-*_])\s*(\1\s*){2,}$', '', text, flags=re.M)  # лінії
    text = re.sub(r'^\s*#{1,6}\s*(.+?)\s*#*\s*$', r'\1.', text, flags=re.M)
    text = re.sub(r'^\s*>\s?', '', text, flags=re.M)

    def numbered(m):
        return f'Пункт {ordinal(int(m.group(1)), "m_nom")}: '
    text = re.sub(r'^\s*(\d{1,2})[.)]\s+', numbered, text, flags=re.M)
    text = re.sub(r'^\s*[-*•●▪]\s+', '', text, flags=re.M)
    text = re.sub(r'(\*\*|__|\*|_|~~|`)(?=\S)(.+?)(?<=\S)\1', r'\2', text)
    text = re.sub(r'[\U0001F000-\U0001FAFF☀-➿️]', '', text)
    # Рядок без кінцевого розділового знака — додати крапку для паузи.
    text = re.sub(r'([^\s.!?:;…,])[ \t]*$', r'\1.', text, flags=re.M)
    return text


# ---------------------------------------------------------------------------
# Основний конвеєр
# ---------------------------------------------------------------------------

ABBREVIATIONS = [
    (r'\bі\s*т\.\s*д\.', 'і так далі'),
    (r'\bі\s*т\.\s*ін\.', 'і таке інше'),
    (r'\bі\s*т\.\s*п\.', 'і тому подібне'),
    (r'\b(у|в)\s*т\.\s*ч\.', r'\1 тому числі'),
    (r'\bнапр\.', 'наприклад'),
    (r'\bдив\.', 'дивіться'),
    (r'\bім\.', 'імені'),
    (r'\bобл\.', 'області'),
    (r'\bр-ну\b', 'району'),
    (r'\bр-н\b', 'район'),
    (r'\bвул\.', 'вулиця'),
    (r'\bпросп\.', 'проспект'),
    (r'\bтел\.', 'телефон'),
    (r'\bрис\.', 'рисунок'),
    (r'\bтабл\.', 'таблиця'),
    (r'\bпроф\.', 'професор'),
    (r'\bд-р\b', 'доктор'),
    (r'\bст\.', 'стаття'),
    (r'\bп\.', 'пункт'),
    (r'\bч\.', 'частина'),
    (r'\bPhD\b', 'доктор філософії'),
    (r'\bАТ\b', 'артеріальний тиск'),
    (r'\bЧСС\b', 'частота серцевих скорочень'),
    (r'\bЧДР\b', 'частота дихальних рухів'),
    (r'\bSpO[2₂]\b', 'сатурація'),
    (r'(?<![A-Za-z])t°?(?=\s*[:=]?\s*[а-яіїєґ])', 'температура'),
    (r'\bNaCl\b', 'натрію хлориду'),
    (r'\bв/в\b', 'внутрішньовенно'),
    (r'\bв/м\b', "внутрішньом'язово"),
    (r'\bп/ш\b', 'підшкірно'),
]

SYMBOLS = [
    ('±', ' плюс-мінус '), ('≈', ' приблизно '), ('≤', ' не більше '),
    ('≥', ' не менше '), ('<', ' менше '), ('>', ' більше '),
    ('&', ' і '), ('§', ' параграф '), ('×', ' на '), ('→', ' — '),
    ('…', '...'), ('/', ' на '),
]

ORD_SUFFIX = {
    'й': 'm_nom', 'ий': 'm_nom', 'ій': 'm_nom', 'го': 'm_gen', 'ого': 'm_gen',
    'му': 'm_loc', 'ому': 'm_loc', 'а': 'f_nom', 'та': 'f_nom', 'ша': 'f_nom',
    'га': 'f_nom', 'я': 'f_nom', 'ої': 'f_gen', 'е': 'n_nom', 'те': 'n_nom',
    'є': 'n_nom', 'ві': 'pl_nom', 'і': 'pl_nom', 'х': 'pl_gen', 'их': 'pl_gen', 'іх': 'pl_gen',
}


def normalize(text):
    text = text.replace('\r\n', '\n')
    text = markdown_to_prose(text)

    # Телефони: +380 67 123 45 67 -> групами
    def phone(m):
        groups = re.findall(r'\d+', m.group(0))
        spoken = []
        for g in groups:
            if g.startswith('0') or len(g) > 3:
                spoken.append(' '.join(UNITS['m'][int(d)] for d in g))
            else:
                spoken.append(cardinal(int(g)))
        lead = 'плюс ' if m.group(0).startswith('+') else ''
        return lead + ', '.join(spoken)
    text = re.sub(r'\+?\b380[\s()\-]*\d{2}[\s()\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}\b', phone, text)
    text = re.sub(r'\(?\b0\d{2}\)?[\s\-]\d{3}[\s\-]\d{2}[\s\-]\d{2}\b', phone, text)

    # Дати: 13.10.2026 (р.)
    def date_num(m):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= d <= 31 and 1 <= mo <= 12):
            return m.group(0)
        return f'{ordinal(d, "n_gen")} {MONTHS_GEN[mo]} {ordinal(y, "m_gen")} року'
    text = re.sub(r'\b(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\s*р(?:оку|\.))?', date_num, text)

    # Дати: 13 жовтня (2026 р.)
    def date_word(m):
        out = f'{ordinal(int(m.group(1)), "n_gen")} {m.group(2)}'
        if m.group(3):
            out += f' {ordinal(int(m.group(3)), "m_gen")} року'
        return out
    text = re.sub(rf'\b(\d{{1,2}})\s+({MONTH_WORDS})(?:\s+(\d{{4}})(?:\s*р(?:оку|\.))?)?',
                  date_word, text)

    # Діапазони років: (у) 1941–1945 рр.
    def year_range(m):
        prep, a, b = m.group(1), int(m.group(2)), int(m.group(3))
        if prep:
            return f'{prep} {ordinal(a, "m_loc")} – {ordinal(b, "m_loc")} роках'
        return f'{ordinal(a, "m_gen")} – {ordinal(b, "m_gen")} років'
    text = re.sub(r'(?:\b(у|в)\s+)?\b(\d{3,4})\s*[–—-]\s*(\d{3,4})\s*(?:рр\.|роках|років|роки)',
                  year_range, text)

    # Рік: (у) 1941 р. / році / року / рік
    def year(m):
        prep, y, word = m.group(1), int(m.group(2)), m.group(3)
        if word == 'рік':
            return f'{ordinal(y, "m_nom")} рік'
        if prep or word == 'році':
            return f'{prep + " " if prep else ""}{ordinal(y, "m_loc")} році'
        return f'{ordinal(y, "m_gen")} року'
    text = re.sub(r'(?:\b(у|в)\s+)?\b(\d{3,4})\s*(р\.|році|року|рік)(?![А-Яа-яІіЇїЄєҐґ])',
                  year, text)

    # Століття: (у) XX ст.
    def century(m):
        prep, n = m.group(1), roman_to_int(m.group(2))
        if prep:
            return f'{prep} {ordinal(n, "n_loc")} столітті'
        return f'{ordinal(n, "n_gen")} століття'
    text = re.sub(r'(?:\b(у|в)\s+)?\b([IVXLC]+)\s*(?:ст\.|стол\.|століття|столітті)',
                  century, text)

    # Час: (о) 14:30
    def clock(m):
        prep, h, mi = m.group(1), int(m.group(2)), m.group(3)
        if h > 24:
            return m.group(0)
        hour = ordinal(h, 'f_loc' if prep else 'f_nom') if h else (
            'нульовій' if prep else 'нульова')
        if mi == '00':
            mins = 'нуль-нуль'
        elif mi.startswith('0'):
            mins = 'нуль ' + UNITS['f'][int(mi)]
        else:
            mins = cardinal(int(mi), 'f')
        return f'{prep + " " if prep else ""}{hour} {mins}'
    text = re.sub(r'(?:\b(о|об)\s+)?\b(\d{1,2}):(\d{2})\b(?!:\d)', clock, text)

    # Артеріальний тиск: 120/80 (мм рт. ст.)
    def pressure(m):
        a, b = cardinal(int(m.group(1))), cardinal(int(m.group(2)))
        tail = ' міліметрів ртутного стовпа' if m.group(3) else ''
        return f'{a} на {b}{tail}'
    text = re.sub(r'\b(\d{2,3})/(\d{2,3})\s*(мм\s*рт\.?\s*ст\.?)?(?=\s|[.,;]|$)',
                  lambda m: pressure(m) if m.group(3) or re.search(
                      r'(АТ|тиск\w*)\s*[:—-]?\s*$', text[:m.start()]) else m.group(0),
                  text)

    # Номер: № 5
    text = re.sub(r'№\s*' + NUM, lambda m: 'номер ' + number_words(m.group(1), m.group(2)), text)

    # Порядкові з нарощенням: 5-й, 3-го, 21-ша
    def ord_suffix(m):
        return ordinal(_int(m.group(1)), ORD_SUFFIX[m.group(2)])
    suf = '|'.join(sorted(ORD_SUFFIX, key=len, reverse=True))
    text = re.sub(rf'\b(\d+)\s*-\s*({suf})(?![А-Яа-яІіЇїЄєҐґ])', ord_suffix, text)

    # Валюта перед числом: $100 -> 100 $
    text = re.sub(r'([$€])\s*' + NUM, lambda m: f'{m.group(2)}{"," + m.group(3) if m.group(3) else ""} {m.group(1)}', text)

    # Діапазон з одиницею: 5–7 км -> від п'яти до семи кілометрів
    def unit_range(m):
        forms, gender = UNIT_TABLE[m.group(5)]
        a = number_words(m.group(1), m.group(2), gender, 'gen')
        b = number_words(m.group(3), m.group(4), gender, 'gen')
        noun = forms[3] if m.group(4) or _is_one(_int(m.group(3))) else forms[2]
        return f'від {a} до {b} {noun}'
    text = re.sub(rf'(?<![\d,.]){NUM}\s*[–—-]\s*{NUM}\s*({UNIT_RE}){UNIT_END}', unit_range, text)

    # Число з одиницею: 2,5 км; 15%; 1 грн
    def num_unit(m):
        sign = m.group(1) or ''
        sign = 'мінус ' if sign in '-−' and sign else ('плюс ' if sign == '+' else '')
        return sign + with_unit(m.group(2), m.group(3), m.group(4))
    text = re.sub(rf'(?:(?<=\s)|(?<=^)|(?<=\())([-−+])?{NUM}\s*({UNIT_RE}){UNIT_END}',
                  num_unit, text, flags=re.M)
    text = re.sub(rf'(?<![\d,.]){NUM}\s*({UNIT_RE}){UNIT_END}',
                  lambda m: with_unit(m.group(1), m.group(2), m.group(3)), text)

    # Діапазон без одиниці: 5–7 -> п'ять-сім
    text = re.sub(rf'(?<![\d,.]){NUM}\s*[–—]\s*{NUM}',
                  lambda m: f'{number_words(m.group(1), m.group(2))}-'
                            f'{number_words(m.group(3), m.group(4))}', text)

    for pattern, repl in ABBREVIATIONS:
        text = re.sub(pattern, repl, text)

    # Решта чисел: знак, ціле або дробове
    def bare(m):
        sign = m.group(1)
        prefix = 'мінус ' if sign in ('-', '−') else ('плюс ' if sign == '+' else '')
        return prefix + number_words(m.group(2), m.group(3))
    text = re.sub(rf'(?:(?<=\s)|(?<=^)|(?<=\())([-−+])(?=\d){NUM}', bare, text, flags=re.M)
    text = re.sub(rf'(?<![\d\w]){NUM}', lambda m: number_words(m.group(1), m.group(2)), text)

    for sym, repl in SYMBOLS:
        text = text.replace(sym, repl)
    text = re.sub(r'[*#_`|\[\]{}]', ' ', text)
    text = re.sub(r'[ \t ]{2,}', ' ', text)
    text = re.sub(r' +([.,;:!?])', r'\1', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip() + '\n'


def report(text):
    """Місця, що потребують ручної вичитки."""
    issues = []
    for m in re.finditer(r'\d+', text):
        issues.append(f'залишилася цифра: «{text[max(0, m.start()-20):m.end()+20]}»')
    for m in re.finditer(r'\b[A-ZА-ЯІЇЄҐ]{2,}\b', text):
        issues.append(f'абревіатура: {m.group(0)}')
    for m in re.finditer(r'\b[A-Za-z]{3,}\b', text):
        issues.append(f'латиниця: {m.group(0)}')
    for m in re.finditer(r'[^\s\w.,;:!?\'"«»()\-–—…]', text):
        issues.append(f'символ: {m.group(0)!r}')
    return sorted(set(issues))


SELFTEST = [
    ('1', 'один'),
    ('21', 'двадцять один'),
    ('1000', 'тисяча'),
    ('2026', 'дві тисячі двадцять шість'),
    ('1 250 000', 'мільйон двісті п\'ятдесят тисяч'),
    ('3,5', "три цілих п'ять десятих"),
    ('1,25', 'одна ціла двадцять п\'ять сотих'),
    ('0,05', "нуль цілих п'ять сотих"),
    ('15%', "п'ятнадцять відсотків"),
    ('3,5 %', "три цілих п'ять десятих відсотка"),
    ('2 год', 'дві години'),
    ('1 грн', 'одна гривня'),
    ('22 км', 'двадцять два кілометри'),
    ('5–7 км', "від п'яти до семи кілометрів"),
    ('-5 °C', "мінус п'ять градусів Цельсія"),
    ('13.10.2026', 'тринадцятого жовтня дві тисячі двадцять шостого року'),
    ('22 червня 1941 р.', 'двадцять другого червня тисяча дев\'ятсот сорок першого року'),
    ('у 1941–1945 рр.', "у тисяча дев'ятсот сорок першому – тисяча дев'ятсот сорок п'ятому роках"),
    ('у 2000 р.', 'у двохтисячному році'),
    ('XX ст.', 'двадцятого століття'),
    ('у III ст.', 'у третьому столітті'),
    ('о 14:30', 'о чотирнадцятій тридцять'),
    ('06:05', 'шоста нуль п\'ять'),
    ('о 06:40:', 'о шостій сорок:'),
    ('t 38,2 °C', 'температура тридцять вісім цілих дві десятих градуса Цельсія'),
    ('АТ 120/80 мм рт. ст.', 'артеріальний тиск сто двадцять на вісімдесят міліметрів ртутного стовпа'),
    ('ЧСС 96 уд/хв', 'частота серцевих скорочень дев\'яносто шість ударів за хвилину'),
    ('№ 5', "номер п'ять"),
    ('3-го', 'третього'),
    ('21-й', 'двадцять перший'),
    ('40-ві роки', 'сорокові роки'),
    ('$100', 'сто доларів'),
    ('і т. д.', 'і так далі'),
]


def selftest():
    failed = 0
    for src, expected in SELFTEST:
        got = normalize(src).strip().rstrip('.')
        if got != expected:
            failed += 1
            print(f'FAIL {src!r}\n  очікувано: {expected}\n  отримано:  {got}')
    print(f'{len(SELFTEST) - failed}/{len(SELFTEST)} тестів пройдено')
    return failed == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('input', nargs='?', default='-', help='файл або - для stdin')
    ap.add_argument('--report', action='store_true',
                    help='вивести в stderr місця для ручної перевірки')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()
    if args.selftest:
        sys.exit(0 if selftest() else 1)
    if args.input == '-':
        src = sys.stdin.read()
    else:
        with open(args.input, encoding='utf-8') as f:
            src = f.read()
    out = normalize(src)
    sys.stdout.write(out)
    if args.report:
        for issue in report(out):
            print('ПЕРЕВІРИТИ:', issue, file=sys.stderr)


if __name__ == '__main__':
    main()
