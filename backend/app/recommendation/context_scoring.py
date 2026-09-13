from __future__ import annotations
import math
from app.models.entities import Movie

DARK={'murder','death','crime','dystopia','horror','suicide','war','violence','revenge','serial killer','grief','tragedy'}
FAST={'chase','heist','martial arts','action','survival','escape','spy','assassin','battle'}
EXPERIMENTAL={'surrealism','avant-garde','experimental','nonlinear timeline','dream','symbolism','absurdism','anthology'}
EMOTIONAL={'grief','family','love','tragedy','trauma','friendship','coming of age','relationship'}

def _signal(movie:Movie,terms:set[str],genre_boost:set[str]|None=None)->float:
    tokens={str(k).casefold() for k in (movie.keywords or [])}|{g.name.casefold() for g in movie.genres}
    text=(movie.overview or '').casefold()
    hits=sum(1 for t in terms if t in tokens or t in text)
    score=min(1.0,hits/2)
    if genre_boost and {g.name for g in movie.genres}&genre_boost:score=max(score,.62)
    return score

def movie_context_dimensions(movie:Movie)->dict[str,float]:
    pop=movie.popularity
    mainstream=.5 if pop is None else min(1.0,math.log1p(max(0,pop))/math.log(101))
    return {
        'darkness':_signal(movie,DARK,{'Horror','Crime','Thriller'}),
        'pace':_signal(movie,FAST,{'Action','Thriller','Adventure'}),
        'experimental':_signal(movie,EXPERIMENTAL),
        'mainstream':mainstream,
        'emotional_intensity':_signal(movie,EMOTIONAL,{'Drama','Romance'}),
    }

def context_adjustment(movie:Movie,targets:dict[str,int|None],company:str|None=None)->float:
    """Return a bounded +/- score adjustment from explicit context sliders.

    A value of 50 is neutral. Extremes reward films whose metadata-derived signal
    is close to the requested target and mildly penalize large mismatches.
    """
    dims=movie_context_dimensions(movie); total=0.0; used=0
    for key,target in targets.items():
        if target is None:continue
        desired=max(0,min(100,target))/100
        closeness=1-abs(dims[key]-desired)
        total+=(closeness-.5)*5.0;used+=1
    if company and company.casefold() in {'family','parents','parent','dad','mom','kids'}:
        genres={g.name for g in movie.genres}
        if genres&{'Family','Animation','Adventure'}:total+=2.0
        if genres&{'Horror'}:total-=2.0
    return max(-10.0,min(10.0,total if used or company else 0.0))
