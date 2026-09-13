import re
import unicodedata
from datetime import date

def normalize_title(value:str)->str:
    value=unicodedata.normalize('NFKD',value or '')
    value=''.join(c for c in value if not unicodedata.combining(c)).casefold().replace('&',' and ')
    return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9]+',' ',value)).strip()
def parse_year(value:object)->int|None:
    m=re.search(r'(?:19|20)\d{2}',str(value or '')); return int(m.group()) if m else None
def parse_rating(value:object)->float|None:
    if value is None or not str(value).strip(): return None
    try:r=float(str(value).strip())
    except ValueError:return None
    if 5<r<=10:r/=2
    if not .5<=r<=5:return None
    return round(r*2)/2
def parse_date(value:object)->date|None:
    if value is None or not str(value).strip(): return None
    try:return date.fromisoformat(str(value).strip()[:10])
    except ValueError:return None
