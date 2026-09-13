import re

GENRES = [
    'science fiction','sci-fi','thriller','horror','drama','comedy','romance','animation','fantasy',
    'mystery','crime','action','adventure','documentary','war','western','musical','family','history'
]
LANGUAGES = {'japanese':'ja','english':'en','french':'fr','spanish':'es','korean':'ko','german':'de','italian':'it','arabic':'ar','hindi':'hi'}


def parse_intent(text):
    raw=(text or '').casefold();out={'genres':[],'avoid':[],'keywords':[]}
    m=re.search(r'(?:under|less than|max(?:imum)?(?: of)?|no more than)\s*(\d{2,3})\s*(?:minutes|mins|min)?',raw)
    if m:out['max_runtime']=int(m.group(1))
    mn=re.search(r'(?:at least|min(?:imum)?(?: of)?)\s*(\d{2,3})\s*(?:minutes|mins|min)',raw)
    if mn:out['min_runtime']=int(mn.group(1))
    h=re.search(r'(?:under|less than|max(?:imum)?(?: of)?)\s*(\d(?:\.\d+)?)\s*hours?',raw)
    if h:out['max_runtime']=int(float(h.group(1))*60)
    if '2 hours' in raw or 'two hours' in raw:out.setdefault('max_runtime',120)
    for g in GENRES:
        label='Science Fiction' if g in {'science fiction','sci-fi'} else g.title()
        if re.search(rf'\b(?:no|not|avoid|without)\s+(?:any\s+)?{re.escape(g)}\b',raw):out['avoid'].append(g)
        elif g in raw:out['genres'].append(label)
    decade=re.search(r'\b(19\d0|20\d0)s\b',raw)
    if decade:out['decade']=int(decade.group(1))
    for name,code in LANGUAGES.items():
        if name in raw:out['language']=code
    if any(x in raw for x in ['with my dad','with my father','with my mom','with my mother','with my parents','with family','family movie']):out['company']='family'
    elif 'with friends' in raw:out['company']='friends'
    elif any(x in raw for x in ['alone','by myself']):out['company']='alone'
    mp={'psychological':['psychological','identity','mind','paranoia'],'weird':['surrealism','experimental','dream'],'dark':['dark','death','crime'],'beautiful':['visual','cinematography','poetic'],'depressing':['grief','tragedy','sad'],'family':['family','adventure','friendship'],'fast':['action','chase','thriller'],'romantic':['romance','relationship'],'funny':['comedy','humor']}
    for word,tags in mp.items():
        if word in raw:out['keywords']+=tags
    # Explicit negative tone/theme phrases override generic keyword detection.
    negative_phrases={
        'not too depressing':['suicide','grief','tragedy'], 'not depressing':['suicide','grief','tragedy'],
        'no gore':['gore'], 'not scary':['horror','ghost','monster'], 'no horror':['horror'],
        'not sad':['grief','tragedy'], 'nothing violent':['violence','murder']
    }
    for phrase,tags in negative_phrases.items():
        if phrase in raw:out['avoid']+=tags
    if 'obscure' in raw or 'hidden gem' in raw:out['popularity_max']=30
    if 'mainstream' in raw or 'popular' in raw:out['popularity_min']=20
    if 'experimental' in raw or 'weird' in raw:out['prefer_experimental']=True
    if 'familiar' in raw or 'safe bet' in raw:out['prefer_experimental']=False
    if 'light' in raw or 'uplifting' in raw or 'feel good' in raw:out['darkness']=20
    if 'dark' in raw:out['darkness']=80
    if 'fast paced' in raw or 'fast-paced' in raw or 'exciting' in raw:out['pace']=80
    if 'slow' in raw or 'meditative' in raw:out['pace']=25
    if 'emotional' in raw or 'intense' in raw or 'devastating' in raw:out['emotional_intensity']=80
    if 'gentle' in raw or 'easy watch' in raw:out['emotional_intensity']=25
    out['genres']=list(dict.fromkeys(out['genres']));out['avoid']=list(dict.fromkeys(out['avoid']));out['keywords']=list(dict.fromkeys(out['keywords']))
    return out
