from app.importers.letterboxd import parse_letterboxd_files
from app.utils.text import normalize_title,parse_rating
def test_normalize_title():assert normalize_title('Amélie & Co.')=='amelie and co'
def test_rating_normalization():assert parse_rating('4.7')==4.5 and parse_rating('9')==4.5 and parse_rating(0) is None
def test_csv_merge_and_rewatch():
    ratings=b'Date,Name,Year,Letterboxd URI,Rating\n2026-01-02,Example Film,2020,https://boxd.it/x,4.5\n';diary=b'Date,Name,Year,Letterboxd URI,Rating,Rewatch\n2026-01-02,Example Film,2020,https://boxd.it/x,4.5,\n2026-03-02,Example Film,2020,https://boxd.it/x,5,Yes\n';r=parse_letterboxd_files([('ratings.csv',ratings),('diary.csv',diary)]);x=r.records[0];assert len(r.records)==1 and x.watched and x.rating==5 and x.rewatch_count>=1 and str(x.last_watched)=='2026-03-02'

def test_zip_export_is_detected():
    import io
    import zipfile
    raw=io.BytesIO()
    with zipfile.ZipFile(raw,'w') as z:
        z.writestr('letterboxd/ratings.csv','Date,Name,Year,Rating\n2026-01-02,Example Film,2020,4\n')
        z.writestr('letterboxd/watchlist.csv','Date,Name,Year\n2026-02-02,Future Film,2024\n')
    r=parse_letterboxd_files([('letterboxd-export.zip',raw.getvalue())])
    assert {x.title for x in r.records}=={'Example Film','Future Film'}
    assert set(r.source_files)=={'ratings.csv','watchlist.csv'}

def test_zip_path_traversal_is_rejected():
    import io
    import zipfile
    raw=io.BytesIO()
    with zipfile.ZipFile(raw,'w') as z:
        z.writestr('../ratings.csv','Date,Name,Year,Rating\n2026-01-02,Evil,2020,4\n')
    try:
        parse_letterboxd_files([('export.zip',raw.getvalue())])
    except ValueError as exc:
        assert 'unsafe path' in str(exc)
    else:
        raise AssertionError('unsafe ZIP path was accepted')
