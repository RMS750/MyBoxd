from app.services.tmdb import TMDBService
def test_match_score_prefers_title_and_year():
    exact={'title':'Arrival','release_date':'2016-11-10','vote_count':10000};wrong={'title':'The Arrival','release_date':'1996-05-31','vote_count':1000};assert TMDBService.match_score('Arrival',2016,exact)>TMDBService.match_score('Arrival',2016,wrong)

def test_match_score_harshly_penalizes_wrong_year():
    exact={'title':'Violet Evergarden','release_date':'2018-01-10','vote_count':5000}
    wrong={'title':'Violet Evergarden','release_date':'2020-09-18','vote_count':5000}
    assert TMDBService.match_score('Violet Evergarden',2018,exact) - TMDBService.match_score('Violet Evergarden',2018,wrong) > .18

def test_search_match_rejects_only_wrong_year_results():
    import asyncio
    service=TMDBService(None)
    async def fake_get(path,params=None):
        return {'results':[{'id':533514,'title':'Violet Evergarden: The Movie','release_date':'2020-09-18','vote_count':5000}]}
    service._get=fake_get
    match,score=asyncio.run(service.search_match('Violet Evergarden',2018))
    assert match is None

def test_reviews_are_normalized():
    import asyncio
    service=TMDBService(None)
    async def fake_get(path,params=None):
        assert path == '/movie/42/reviews'
        return {'results':[{'id':'r1','author':'Alice','author_details':{'username':'alice','rating':8.0},'content':'Thoughtful review','created_at':'2026-01-01T00:00:00Z','url':'https://example.test/review'}]}
    service._get=fake_get
    rows=asyncio.run(service.reviews(42))
    assert rows[0]['author']=='Alice'
    assert rows[0]['rating']==8.0
    assert rows[0]['content']=='Thoughtful review'


def test_sqlite_tmdb_cache_write_stays_in_memory(monkeypatch):
    """Local SQLite cache writes must not compete with movie updates."""
    import app.services.tmdb as tmdb_module

    def fail_session():
        raise AssertionError("SQLite TMDB cache should not open a writer connection")

    monkeypatch.setattr(tmdb_module, "SessionLocal", fail_session)
    key = "tmdb:test:sqlite-memory-cache"
    payload = {"results": [{"id": 1}]}
    tmdb_module.TMDBService._cache_write(key, payload)
    assert tmdb_module._MEMORY_CACHE[key] == payload
