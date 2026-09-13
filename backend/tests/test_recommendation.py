from types import SimpleNamespace
from app.recommendation.features import feature_dict
from app.recommendation.rating_predictor import PersonalRatingPredictor
class Movie:
    def __init__(self,title,genres,year=2020):
        self.title=title;self.genres=[SimpleNamespace(name=g) for g in genres];self.year=year;self.runtime=120;self.popularity=20;self.vote_average=7;self.vote_count=500;self.keywords=[];self.original_language='en';self.production_countries=['United States of America'];self.overview='A character faces a strange mystery.';self.director_names=[];self.actor_names=[]
def test_feature_dict():assert 'runtime_scaled' in feature_dict(Movie('X',['Drama']))
def test_predictor_runs():
    items=[SimpleNamespace(movie=Movie(str(i),['Drama'] if i<5 else ['Comedy'],2010+i),rating=4.5 if i<5 else 2.) for i in range(10)];p=PersonalRatingPredictor(items).predict_many([Movie('new',['Drama'])])[0];assert .5<=p.rating<=5 and p.method in {'personal-ensemble','personal-neighbours'}

def test_hybrid_ranker_returns_explainable_score():
    from app.models.entities import Genre,Movie
    from app.recommendation.hybrid_ranker import rank_movies
    genre=Genre(name='Drama')
    def mk(mid,title,rating=None):
        m=Movie(id=mid,title=title,normalized_title=title.lower(),year=2020+mid,runtime=110,popularity=20,vote_average=7.5,vote_count=500,overview='A character-driven mystery about identity.',original_language='en',production_countries=['United States of America'],keywords=['identity'])
        m.genres=[genre]
        return SimpleNamespace(movie_id=mid,movie=m,rating=rating,watched=rating is not None,watchlist=False)
    history=[mk(i,f'Film {i}',4.0+(i%2)*.5) for i in range(1,9)]
    candidate=mk(20,'Candidate').movie
    row=rank_movies(history,[candidate])[0]
    assert 0<=row['match_score']<=100
    assert .5<=row['predicted_rating']<=5
    assert row['category'] in {'SAFE BET','GOOD MATCH','WILD CARD','RISKY PICK'}
    assert row['explanation']


def test_relative_taste_profile_separates_loved_and_disliked_genres():
    from app.services.taste import build_taste_profile
    from app.models.entities import Genre, Movie
    from datetime import datetime
    drama=Genre(name='Drama'); action=Genre(name='Action')
    rows=[]
    for i in range(8):
        m=Movie(id=100+i,title=f'Drama {i}',normalized_title=f'drama {i}',year=2010+i,runtime=110,popularity=20,vote_average=7,vote_count=500,overview='identity character study',original_language='en',production_countries=['US'],keywords=['identity'],metadata_updated_at=datetime.now())
        m.genres=[drama]
        rows.append(SimpleNamespace(movie_id=m.id,movie=m,rating=4.5,watched=True,watchlist=False,rewatch_count=0))
    for i in range(8):
        m=Movie(id=200+i,title=f'Action {i}',normalized_title=f'action {i}',year=2010+i,runtime=110,popularity=20,vote_average=7,vote_count=500,overview='chase mission',original_language='en',production_countries=['US'],keywords=['chase'],metadata_updated_at=datetime.now())
        m.genres=[action]
        rows.append(SimpleNamespace(movie_id=m.id,movie=m,rating=2.0,watched=True,watchlist=False,rewatch_count=0))
    profile=build_taste_profile(rows)
    assert profile['genre_scores']['Drama'] > 0.5
    assert profile['genre_scores']['Action'] < -0.5


def test_ranker_has_real_score_spread_and_safe_bets():
    from app.models.entities import Genre, Movie
    from app.recommendation.hybrid_ranker import rank_movies
    from datetime import datetime
    drama=Genre(name='Drama'); thriller=Genre(name='Thriller'); action=Genre(name='Action')
    def make(mid,title,genres,keywords):
        m=Movie(id=mid,title=title,normalized_title=title.lower(),year=2020,runtime=110,popularity=20,vote_average=7.5,vote_count=1000,overview=' '.join(keywords),original_language='en',production_countries=['US'],keywords=keywords,metadata_updated_at=datetime.now())
        m.genres=genres
        return m
    history=[]
    for i in range(30):
        m=make(300+i,f'Love {i}',[drama,thriller],['psychological','identity'])
        history.append(SimpleNamespace(movie_id=m.id,movie=m,rating=4.5+(i%2)*.5,watched=True,watchlist=False,rewatch_count=0))
    for i in range(30):
        m=make(400+i,f'Dislike {i}',[action],['chase','mission'])
        history.append(SimpleNamespace(movie_id=m.id,movie=m,rating=1.5+(i%2)*.5,watched=True,watchlist=False,rewatch_count=0))
    good=make(900,'Good candidate',[drama,thriller],['psychological','identity'])
    bad=make(901,'Bad candidate',[action],['chase','mission'])
    ranked=rank_movies(history,[good,bad])
    by_title={row['movie'].title:row for row in ranked}
    assert by_title['Good candidate']['match_score'] - by_title['Bad candidate']['match_score'] >= 35
    assert by_title['Good candidate']['predicted_rating'] > by_title['Bad candidate']['predicted_rating'] + 1.5
    assert by_title['Good candidate']['category'] == 'SAFE BET'
    assert by_title['Bad candidate']['category'] == 'RISKY PICK'


def test_very_low_letterboxd_rating_is_not_a_70_match():
    from app.models.entities import Genre, Movie
    from app.recommendation.hybrid_ranker import rank_movies
    from datetime import datetime
    drama=Genre(name='Drama')
    history=[]
    for i in range(24):
        m=Movie(id=1000+i,title=f'History {i}',normalized_title=f'history {i}',year=2010+i%10,runtime=110,popularity=25,vote_average=7,vote_count=1000,overview='character mystery',original_language='en',production_countries=['US'],keywords=['identity'],metadata_updated_at=datetime.now())
        m.genres=[drama]
        history.append(SimpleNamespace(movie_id=m.id,movie=m,rating=4.0 if i<12 else 3.0,watched=True,watchlist=False,rewatch_count=0))
    candidate=Movie(id=1999,title='Bad public reception',normalized_title='bad public reception',year=2020,runtime=110,popularity=70,vote_average=6.8,vote_count=5000,overview='generic romance crime',original_language='en',production_countries=['US'],keywords=['romance'],metadata_updated_at=datetime.now(),letterboxd_rating=1.7,letterboxd_rating_count=50000)
    candidate.genres=[]
    row=rank_movies(history,[candidate])[0]
    assert row['match_score'] <= 38
    assert row['category'] == 'RISKY PICK'


def test_match_scores_are_smooth_not_bucketed_by_letterboxd_rating():
    from app.models.entities import Genre, Movie
    from app.recommendation.hybrid_ranker import rank_movies
    from datetime import datetime
    drama=Genre(name='Drama')
    history=[]
    for i in range(36):
        m=Movie(id=3000+i,title=f'History smooth {i}',normalized_title=f'history smooth {i}',year=2000+i%20,runtime=112,popularity=22,vote_average=7.2,vote_count=1000,overview='character identity relationship',original_language='en',production_countries=['US'],keywords=['identity','relationship'],metadata_updated_at=datetime.now())
        m.genres=[drama]
        history.append(SimpleNamespace(movie_id=m.id,movie=m,rating=4.5 if i<18 else 2.5,watched=True,watchlist=False,rewatch_count=0))
    candidates=[]
    for idx,lb in enumerate([1.6,1.8,2.0,2.2,2.5,2.8,3.1,3.4,3.7,4.0,4.3]):
        m=Movie(id=4000+idx,title=f'Candidate {lb}',normalized_title=f'candidate {lb}',year=2020,runtime=112,popularity=22,vote_average=6.5,vote_count=1000,overview='character identity relationship',original_language='en',production_countries=['US'],keywords=['identity','relationship'],metadata_updated_at=datetime.now(),letterboxd_rating=lb,letterboxd_rating_count=50000)
        m.genres=[drama]
        candidates.append(m)
    rows=rank_movies(history,candidates)
    scores={float(row['movie'].letterboxd_rating):float(row['match_score']) for row in rows}
    ordered=[scores[x] for x in sorted(scores)]
    assert all(b >= a for a,b in zip(ordered,ordered[1:]))
    assert len(set(ordered)) >= 9
    assert ordered[-1] - ordered[0] >= 35
    # Nearby public ratings should move the score gradually, not snap to a cap.
    assert abs(scores[1.8]-scores[1.6]) < 12
    assert abs(scores[2.2]-scores[2.0]) < 12
