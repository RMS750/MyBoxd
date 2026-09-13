import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error,mean_squared_error,r2_score
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.model_selection import train_test_split
from app.recommendation.features import feature_dict,movie_text
def _m(name,y,p,n):return {'model':name,'mae':round(float(mean_absolute_error(y,p)),3),'rmse':round(float(np.sqrt(mean_squared_error(y,p))),3),'r2':round(float(r2_score(y,p)),3) if len(y)>=3 and len(set(y.tolist()))>1 else None,'train_size':n,'test_size':len(y)}
def evaluate(interactions,test_size=.2):
    rated=[x for x in interactions if x.rating is not None]
    if len(rated)<10:return {'ready':False,'message':'At least 10 rated movies are needed for a meaningful held-out evaluation.','results':[]}
    idx=np.arange(len(rated));tr,te=train_test_split(idx,test_size=max(2,int(len(rated)*test_size)),random_state=42);train=[rated[i] for i in tr];test=[rated[i] for i in te];yt=np.array([x.rating for x in train],float);yv=np.array([x.rating for x in test],float);res=[_m('Baseline average',yv,np.full_like(yv,yt.mean()),len(train))]
    def ridge(name,genre=False):
        features=[feature_dict(x.movie,genre) for x in train]
        if not any(features):
            pred=np.full_like(yv,yt.mean())
            res.append(_m(name,yv,pred,len(train)))
            return pred
        v=DictVectorizer(sparse=True);X=v.fit_transform(features);Xt=v.transform([feature_dict(x.movie,genre) for x in test]);pred=np.clip(Ridge(alpha=6).fit(X,yt).predict(Xt),.5,5);res.append(_m(name,yv,pred,len(train)));return pred
    ridge('Genre-only',True);meta=ridge('Metadata Ridge');tf=TfidfVectorizer(stop_words='english',max_features=5000,ngram_range=(1,2));A=tf.fit_transform([movie_text(x.movie) for x in train]);B=tf.transform([movie_text(x.movie) for x in test]);sims=cosine_similarity(B,A);sem=[]
    for row in sims:
        top=np.argsort(row)[-5:];w=row[top];sem.append(float(np.average(yt[top],weights=w)) if w.sum()>0 else float(yt.mean()))
    sem=np.clip(np.array(sem),.5,5);res.append(_m('Semantic TF-IDF',yv,sem,len(train)));hy=np.clip(.65*meta+.35*sem,.5,5);res.append(_m('Hybrid',yv,hy,len(train)));points=[{'title':test[j].movie.title,'actual':round(float(yv[j]),2),'predicted':round(float(hy[j]),2)} for j in range(len(test))];res.sort(key=lambda x:x['mae']);return {'ready':True,'best_model':res[0]['model'],'results':res,'predicted_vs_actual':points}
