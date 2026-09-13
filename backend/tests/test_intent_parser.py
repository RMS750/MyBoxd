from app.recommendation.intent_parser import parse_intent


def test_natural_language_watch_tonight_parser():
    parsed=parse_intent('I have two hours and want something psychological and weird but not depressing, with my dad, maybe a Japanese 1990s thriller.')
    assert parsed['max_runtime']==120
    assert parsed['language']=='ja'
    assert parsed['decade']==1990
    assert parsed['company']=='family'
    assert 'Thriller' in parsed['genres']
    assert 'grief' in parsed['avoid']
    assert parsed['prefer_experimental'] is True
