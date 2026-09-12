from fractions import Fraction
import random, collections

def dhondt(counts, slots=3):
    s=[0]*10; out=[]
    for _ in range(slots):
        best=None
        for d in range(10):
            q=Fraction(counts[d], s[d]+1)
            if best is None or q>best[0]:
                best=(q,d)          # strict > keeps the LOWER digit on ties
        s[best[1]]+=1; out.append(best[1])
    return out

def c(**kw):
    a=[0]*10
    for k,v in kw.items(): a[int(k[1:])]=v
    return a

# verify the three worked examples from the PDF
print("2:300,7:95 ->", dhondt(c(d2=300,d7=95)), "expect [2,2,2]")
print("1:100,2:99 ->", dhondt(c(d1=100,d2=99)), "expect [1,2,1]")
print("all zero   ->", dhondt([0]*10),          "expect [0,0,0]")

# outcome SHAPE distribution under different voter behaviours
def shape(r):
    u=len(set(r))
    return {1:"AAA repdigit",2:"AAB two-digit",3:"ABC three-digit"}[u]

def run(label, sampler, n=20000, trials=3000):
    tally=collections.Counter()
    for _ in range(trials):
        tally[shape(dhondt(sampler(n)))]+=1
    tot=sum(tally.values())
    print(f"\n{label}")
    for k,v in tally.most_common():
        print(f"   {k:<16} {100*v/tot:5.1f}%")

def uniform(n):
    a=[0]*10
    for _ in range(n): a[random.randrange(10)]+=1
    return a

def coordinated(n, lead=0.25):
    # one digit attracts `lead` share, rest split the remainder uniformly
    a=[0]*10; top=random.randrange(10)
    for _ in range(n):
        a[top if random.random()<lead else random.randrange(10)]+=1
    return a

run("uniform random voting (no coordination)", uniform)
run("mild coordination: one digit pulls 25%", lambda n: coordinated(n,0.25))
run("real coordination: one digit pulls 40%", lambda n: coordinated(n,0.40))
