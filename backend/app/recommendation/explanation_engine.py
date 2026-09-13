LABELS={'genre':'genre fit','semantic':'story/theme similarity','creator':'director/cast fit','decade':'era preference','locale':'country/language fit','runtime':'runtime fit','popularity':'mainstream/obscure fit','community':'Letterboxd/community reception','predicted_rating':'predicted personal rating','novelty':'novelty'}
def explain(movie,components,liked,profile):
    strongest=[k for k,_ in sorted(components.items(),key=lambda x:x[1],reverse=True) if k in LABELS][:3];genres=[g.name for g in movie.genres];top=[g for g,s in profile.get('genre_scores',{}).items() if s>0.12][:5];over=[g for g in genres if g in top];refs=[x.movie.title for x in liked if set(g.name for g in x.movie.genres)&set(genres)][:2];parts=[]
    if over:parts.append(f"It matches your strong preference for {', '.join(over[:2])}")
    if 'semantic' in strongest and refs:parts.append(f"its themes are close to highly rated films in your library such as {', '.join(refs)}")
    if 'creator' in strongest and movie.director_names:parts.append(f"its creator signal is strong, led by {movie.director_names[0]}")
    if 'runtime' in strongest and movie.runtime:parts.append(f"its {movie.runtime}-minute runtime is close to your usual sweet spot")
    if 'community' in strongest and getattr(movie,'letterboxd_rating',None):parts.append(f"its Letterboxd average is {movie.letterboxd_rating:.2f}/5")
    elif 'community' in strongest and movie.vote_average:parts.append(f"its TMDB audience score is {movie.vote_average:.1f}/10")
    if not parts:parts.append('Its strongest signals are '+(', '.join(LABELS[k] for k in strongest) or 'overall profile similarity'))
    s='; '.join(parts[:3])+'.';return s[0].upper()+s[1:]
