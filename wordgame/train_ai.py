"""Train a Scrabble NPC gate using heuristic concepts or labelled JSONL data.

Bootstrap mode teaches an explicit heuristic on synthetic concept combinations;
its metrics do NOT measure playing strength or real-game win probabilities.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from .npc import CARDINALITIES,CircuitRouter


def synthetic(samples,seed):
    rng = np.random.default_rng(seed)
    total = int(np.prod(CARDINALITIES))
    ids = rng.choice(total,min(samples,total),replace=False)
    x = np.array(np.unravel_index(ids,CARDINALITIES)).T
    teacher = 8*x[:,0]+3*x[:,1]+2*x[:,2]-6*x[:,3]-4*x[:,4]+2*x[:,5]
    teacher += np.where((x[:,5]==2)&(x[:,2]>=5),10,0)
    y = np.digitize(teacher,[25,48])
    return x,y


def load_records(path):
    records = [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
    x = np.asarray([r['concepts'] for r in records])
    y = np.asarray([r['quality'] for r in records])
    if x.ndim!=2 or x.shape[1]!=6 or not np.issubdtype(x.dtype,np.integer) or not np.issubdtype(y.dtype,np.integer):
        raise ValueError('Each record needs six integer concepts and integer quality (0, 1 or 2).')
    if any(np.any((x[:,j]<0)|(x[:,j]>=k)) for j,k in enumerate(CARDINALITIES)) or np.any((y<0)|(y>2)):
        raise ValueError('Record contains out-of-range concepts or quality.')
    return x,y


def fit_model(x,y,output,seed=42,epochs=300,source='synthetic heuristic teacher'):
    rng = np.random.default_rng(seed)
    # Keep identical coarse concept vectors together to avoid partition leakage.
    groups,inverse = np.unique(x,axis=0,return_inverse=True)
    if len(groups)<30:
        raise ValueError('Provide at least 30 distinct concept vectors.')
    order = rng.permutation(len(groups))
    first,second = int(.6*len(groups)),int(.8*len(groups))
    masks = [np.isin(inverse,ids) for ids in (order[:first],order[first:second],order[second:])]
    train,gate,test = masks
    print(f'Source: {source}. Split: {train.sum()} expert / {gate.sum()} gate / {test.sum()} held-out samples.',flush=True)
    progress = lambda epoch,total,loss:print(f'Gate {epoch}/{total} | fitting NLL {loss:.4f}',flush=True)
    model = CircuitRouter.fit(x[train],y[train],x[gate],y[gate],seed,epochs,progress)
    p,_ = model.predict(x[test])
    expert = model.experts(x[test])
    labels = y[test]
    nll = lambda probs:float(-np.log(np.clip(probs,1e-12,1)).mean())
    correct = expert[np.arange(len(labels)),:,labels]
    loss,oracle = nll(p[np.arange(len(labels)),labels]),nll(correct.max(1))
    report = {'source':source,'seed':seed,'epochs':epochs,'samples':len(x),'concept_groups':len(groups),
              'held_out_samples':len(labels),'nll':loss,'uniform_nll':nll(correct.mean(1)),
              'oracle_nll':oracle,'routing_regret':loss-oracle,'accuracy':float((p.argmax(1)==labels).mean()),
              'caveat':'Quality labels are teacher judgments, not measured wins. No playing-strength claim.'}
    output = Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    model.save(output)
    output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)
    print(f'Saved {output}',flush=True)
    return model,report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default=str(Path(__file__).resolve().parents[1]/'models'/'scrabble-npc.npz'))
    parser.add_argument('--data',help='Optional JSONL with concepts and quality labels.')
    parser.add_argument('--samples',type=int,default=12000)
    parser.add_argument('--epochs',type=int,default=300)
    parser.add_argument('--seed',type=int,default=42)
    args = parser.parse_args()
    if args.epochs<1 or args.samples<30:
        parser.error('Use positive epochs and at least 30 samples.')
    x,y = load_records(args.data) if args.data else synthetic(args.samples,args.seed)
    fit_model(x,y,args.output,args.seed,args.epochs,'labelled JSONL quality judgments' if args.data else 'synthetic heuristic teacher')


if __name__=='__main__':
    main()
