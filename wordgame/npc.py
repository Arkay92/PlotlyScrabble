"""Chess v18-style categorical circuits and posterior-evidence neural gate.

Scrabble classes represent weak/balanced/strong teacher-rated move quality,
NOT probabilities of winning. No chess weights or imports are used here.
"""
import numpy as np

CARDINALITIES = (9,5,8,3,5,3)
SCHEMA = 'scrabble-quality-v1'


def softmax(x):
    e = np.exp(x-np.max(x,axis=-1,keepdims=True))
    return e/e.sum(axis=-1,keepdims=True)


def gate_features(p):
    mean = p.mean(axis=1,keepdims=True)
    ordered = np.sort(p,axis=-1)
    return np.concatenate([-(p*np.log(p+1e-12)).sum(-1),ordered[:,:,-1]-ordered[:,:,-2],
                           p[:,:,2],p[:,:,0],(p*np.log((p+1e-12)/(mean+1e-12))).sum(-1)],axis=1)


class CircuitRouter:
    def __init__(self,prior,leaves,w1,b1,w2,b2,mean,scale):
        self.prior,self.leaves = prior,leaves
        self.w1,self.b1,self.w2,self.b2 = w1,b1,w2,b2
        self.mean,self.scale = mean,scale

    def experts(self,x):
        x = np.asarray(x,dtype=int)
        if x.ndim!=2 or x.shape[1]!=len(CARDINALITIES) or any(
                np.any((x[:,j]<0)|(x[:,j]>=k)) for j,k in enumerate(CARDINALITIES)):
            raise ValueError('Invalid Scrabble concept array.')
        logp = np.broadcast_to(np.log(self.prior),(len(x),*self.prior.shape)).copy()
        for j,leaf in enumerate(self.leaves):
            logp += np.log(leaf[:,:,x[:,j]].transpose(2,0,1))
        return softmax(logp)

    def predict(self,x):
        p = self.experts(x)
        f = (gate_features(p)-self.mean)/self.scale
        weights = softmax(np.tanh(f@self.w1+self.b1)@self.w2+self.b2)
        return (p*weights[:,:,None]).sum(1),weights

    def save(self,path):
        np.savez_compressed(path,schema=SCHEMA,prior=self.prior,w1=self.w1,b1=self.b1,w2=self.w2,b2=self.b2,
                            mean=self.mean,scale=self.scale,**{f'leaf{j}':v for j,v in enumerate(self.leaves)})

    @classmethod
    def load(cls,path):
        with np.load(path,allow_pickle=False) as d:
            if str(d['schema'])!=SCHEMA:
                raise ValueError('This model is not a compatible Scrabble NPC model.')
            model = cls(d['prior'],[d[f'leaf{j}'] for j in range(len(CARDINALITIES))],
                        *(d[k] for k in ('w1','b1','w2','b2','mean','scale')))
        expected = [(model.prior,(3,3)),(model.w1,(15,16)),(model.b1,(16,)),
                    (model.w2,(16,3)),(model.b2,(3,)),(model.mean,(15,)),(model.scale,(15,))]
        expected += [(leaf,(3,3,k)) for leaf,k in zip(model.leaves,CARDINALITIES)]
        if any(a.shape!=shape or not np.isfinite(a).all() for a,shape in expected) or np.any(model.scale<=0):
            raise ValueError('Invalid NPC model shapes or parameters.')
        for probabilities in [model.prior,*model.leaves]:
            if np.any(probabilities<=0) or not np.allclose(probabilities.sum(-1),1):
                raise ValueError('Invalid circuit probabilities.')
        return model

    @classmethod
    def fit(cls,x,y,gx,gy,seed=42,epochs=300,progress=None):
        if len(x)==0 or len(gx)==0 or epochs<1:
            raise ValueError('Training and gate samples and positive epochs are required.')
        rng = np.random.default_rng(seed)
        prior = np.ones((3,3))
        leaves = [np.ones((3,3,k)) for k in CARDINALITIES]
        # Score / rack / defence specialists see different training regimes.
        regimes = [1+x[:,0]/4,1+x[:,1]/2,1+x[:,4]/2]
        for expert,regime in enumerate(regimes):
            indices = rng.choice(len(x),len(x),replace=True,p=regime/regime.sum())
            for j in indices:
                prior[expert,y[j]] += 1
                for concept,category in enumerate(x[j]):
                    leaves[concept][expert,y[j],category] += 1
        prior /= prior.sum(-1,keepdims=True)
        leaves = [v/v.sum(-1,keepdims=True) for v in leaves]
        model = cls(prior,leaves,rng.normal(0,.1,(15,16)),np.zeros(16),rng.normal(0,.1,(16,3)),np.zeros(3),0,1)
        p = model.experts(gx)
        f = gate_features(p)
        model.mean,model.scale = f.mean(0),np.maximum(f.std(0),1e-6)
        f = (f-model.mean)/model.scale
        true_p = p[np.arange(len(p)),:,gy]
        for epoch in range(epochs):
            h = np.tanh(f@model.w1+model.b1)
            weights = softmax(h@model.w2+model.b2)
            mixture = (weights*true_p).sum(1,keepdims=True)
            grad = weights*(1-true_p/np.maximum(mixture,1e-12))/len(f)
            dh = (grad@model.w2.T)*(1-h*h)
            model.w2 -= .05*h.T@grad
            model.b2 -= .05*grad.sum(0)
            model.w1 -= .05*f.T@dh
            model.b1 -= .05*dh.sum(0)
            if progress and (epoch==0 or (epoch+1)%25==0 or epoch+1==epochs):
                progress(epoch+1,epochs,float(-np.log(np.maximum(mixture,1e-12)).mean()))
        return model
