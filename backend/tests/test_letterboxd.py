from app.services.letterboxd import _parse_json_ld


def test_letterboxd_json_ld_rating_parser():
    page='''<html><script type="application/ld+json">{"@type":"Movie","aggregateRating":{"@type":"AggregateRating","ratingValue":1.82,"ratingCount":12345}}</script></html>'''
    parsed=_parse_json_ld(page)
    assert parsed == {"rating": 1.82, "rating_count": 12345}
