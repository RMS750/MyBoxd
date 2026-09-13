import math
from app.models.entities import Movie
def movie_text(m:Movie):return ' '.join([m.title,m.overview or '',' '.join(g.name for g in m.genres),' '.join(m.keywords or []),' '.join(m.director_names),' '.join(m.actor_names[:5])])
def feature_dict(m:Movie,genre_only:bool=False):
    f={f'genre={g.name}':1. for g in m.genres}
    if genre_only:return f
    f.update({f'keyword={k}':1. for k in (m.keywords or [])[:20]});f.update({f'director={d}':1. for d in m.director_names[:2]});f.update({f'actor={a}':1. for a in m.actor_names[:5]})
    if m.original_language:f[f'language={m.original_language}']=1.
    for c in (m.production_countries or [])[:3]:f[f'country={c}']=1.
    if m.year:f[f'decade={(m.year//10)*10}']=1.;f['year_scaled']=(m.year-1950)/100
    if m.runtime:f['runtime_scaled']=m.runtime/180
    effective_popularity=m.popularity if m.popularity is not None else getattr(m,'catalog_popularity',None)
    if effective_popularity is not None:f['log_popularity']=math.log1p(max(0,effective_popularity))/6
    if getattr(m,'catalog_rating',None) is not None:f['audience_rating']=float(m.catalog_rating)/5
    elif m.vote_average is not None:f['audience_rating']=m.vote_average/10
    effective_count=getattr(m,'catalog_rating_count',None) or m.vote_count
    if effective_count is not None:f['log_vote_count']=math.log1p(max(0,effective_count))/12
    return f
