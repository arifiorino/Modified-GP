#!/usr/bin/python3
import csv, datetime, numpy as np, matplotlib.pyplot as plt, torch, os

ucb_mult = 1
GP_ERROR = 0.05
RBF_SIGMA = 1
def GP(xs, F, x):
  xs1 = torch.pow(xs,2)@torch.ones((xs.size()[1],1)).to('cuda')
  xs2 = torch.cat([torch.t(xs1)]*xs.size()[0])
  M = xs2 - 2*(xs @ torch.t(xs)) + torch.t(xs2)
  M = torch.exp(-M/(2*RBF_SIGMA**2))
  M += GP_ERROR * torch.eye(xs.size()[0]).to('cuda')
  x1 = torch.pow(x,2)@torch.ones((x.size()[1],1)).to('cuda')
  x2 = torch.cat([torch.t(x1)]*xs.size()[0])
  xs3 = torch.cat([torch.t(xs1)]*x.size()[0])
  v = torch.t(x2) - 2*(x @ torch.t(xs)) + xs3
  v = torch.exp(-v/(2*RBF_SIGMA**2))
  temp = v @ torch.linalg.inv(M)
  mean = temp @ F
  var = torch.ones(mean.size()).to('cuda')
  var -= (temp*v)@torch.ones((temp.size()[1],1)).to('cuda')
  stdev = torch.sqrt(var)
  return (mean.cpu().numpy(), stdev.cpu().numpy())

with open('United_States_COVID-19_Cases_and_Deaths_by_State_over_Time.csv', 'r') as f:
  rows=[list(row) for row in csv.reader(f)][1:]
rows = [[datetime.datetime.strptime(row[0], '%m/%d/%Y')]+row[1:-3] for row in rows]
rows.sort(key=lambda s:s[0])
# filter before 11/2021, after 7/2020
rows = [row for row in rows if row[0]<=datetime.datetime(year=2021,month=11,day=1)]
rows = [row for row in rows if row[0]>=datetime.datetime(year=2020,month=10,day=1)]
states=set([row[1] for row in rows])
cases,deaths=None,None
for state in states:
  if cases is None:
    cases=np.array([int(row[2]) for row in rows if row[1]==state])
    deaths=np.array([int(row[7]) for row in rows if row[1]==state])
  else:
    cases+=np.array([int(row[2]) for row in rows if row[1]==state])
    deaths+=np.array([int(row[7]) for row in rows if row[1]==state])
# cumulative -> daily
cases = [(cases[i+1]-cases[i]) for i in range(len(cases)-1)]
deaths = [(deaths[i+1]-deaths[i]) for i in range(len(deaths)-1)]
# weekly average
cases = [sum(cases[i:i+7])/7 for i in range(len(cases)-7)]
deaths = [sum(deaths[i:i+7])/7 for i in range(len(deaths)-7)]
avg_cases=sum(cases)/len(cases)
avg_deaths=sum(deaths)/len(deaths)
# normalize
cases = [case/avg_cases for case in cases]
deaths = [death/avg_deaths for death in deaths]
# dates
dates=[row[0] for row in rows if row[1]==list(states)[0]][:len(cases)]

d_sort = sorted(deaths)
nBins=5
binLen = len(d_sort)/nBins
bins=[sum(d_sort[int(i*binLen):int((i+1)*binLen)])/binLen for i in range(nBins)]

def plot():
  bins2=[d_sort[int(i*binLen)] for i in range(nBins)]+[d_sort[-1]]
  def b(x):
    for i in range(nBins):
      if x<=bins2[i+1]:
        return i
    raise ValueError()
  fig, ax = plt.subplots()
  ax.plot(dates, cases)
  ax2 = ax.twinx()
  ax2.plot(dates, deaths)
  ax2.plot(dates, [bins[b(death)] for death in deaths])
  plt.show()

def itol(idx, mods):
  r=[]
  for i in range(len(mods)):
    r.append(idx % mods[i])
    idx //= mods[i]
  return r

gCases, gDeaths = cases, deaths
nCases = 30
nDeaths = 6
nLosses = 4

def f(deathI, deaths):
  diff = np.abs(deaths-np.array(gDeaths[deathI:deathI+nDeaths]))
  losses = np.zeros(nLosses)
  for i in range(nDeaths-nLosses+1):
    losses+=diff[i:i+nLosses]
  return (losses/(nDeaths-nLosses+1)).tolist()

#with open('caseIs.csv','r') as fi:
  #allCaseIs=[[int(x) for x in row] for row in csv.reader(fi)]
#with open('starts.csv','r') as fi:
  #starts=[[int(x) for x in row] for row in csv.reader(fi)]
points=[]
for expI in range(1):
  print('exp',expI)
  #caseIs = allCaseIs[expI]
  caseIs = np.random.randint(len(gCases)-nCases+1,size=101).tolist()
  #past_in = [[bins[i] for i in starts[expI]]]
  past_in = [np.random.choice(bins, nDeaths).tolist()]
  past_out = [[sum(f(caseIs[0] + (nCases-nDeaths), past_in[0]))]]
  train_x, train_y = [], []
  for t in range(100):
    caseI = caseIs[t+1]
    #print(''.join(['%7.2f'%a for a in [t]+gCases[caseI:caseI+nCases]+past_in[-1]+[sum(past_out[-1])]]))
    train_x.append(gCases[caseIs[t]:caseIs[t]+nCases])
    train_x[-1].extend(past_in[t])
    train_y.append([sum(past_out[t])])
    test_x=[]
    for idx in range(nBins**nDeaths):
      a=[bins[i] for i in itol(idx,[nBins]*nDeaths)]
      test_x.append(gCases[caseI:caseI+nCases]+a)
    mean, stdev = GP(torch.Tensor(train_x).to('cuda'), torch.Tensor(train_y).to('cuda'), torch.Tensor(test_x).to('cuda'))
    best_x=None
    best_y=1e10
    for idx in range(nBins**nDeaths):
      y=mean[idx][0]-ucb_mult*stdev[idx][0]
      if y<best_y:
        best_x=itol(idx,[nBins]*nDeaths)
        best_y=y
    best_x = [bins[i] for i in best_x]
    for i in range(nDeaths):
      points.append([dates[caseI+nCases-nDeaths+i],best_x[i]])
    past_in.append(best_x)
    past_out.append(f(caseI + (nCases-nDeaths), np.array(best_x)))

  # APPEND MODE
  filename='A2.csv'
  data=[]
  if os.path.isfile(filename):
    with open(filename, 'r') as fi:
      data=[list(row) for row in csv.reader(fi)]
  if len(data)==0:
    data=[[] for _ in past_out]
  with open(filename, 'w') as fi:
    csv.writer(fi).writerows([data[i]+[sum(x)] for i,x in enumerate(past_out)])
with open('actual.csv','w') as fi:
  csv.writer(fi).writerows([[dates[i],d] for i,d in enumerate(gDeaths)])
with open('points.csv','w') as fi:
  csv.writer(fi).writerows(points)

print("PREDICTING DEATHS")
points=[]
for caseI in range(0,len(gCases)-nCases,nDeaths):
  print(caseI)
  test_x=[]
  for idx in range(nBins**nDeaths):
    a=[bins[i] for i in itol(idx,[nBins]*nDeaths)]
    test_x.append(gCases[caseI:caseI+nCases]+a)
  mean, stdev = GP(torch.Tensor(train_x).to('cuda'), torch.Tensor(train_y).to('cuda'), torch.Tensor(test_x).to('cuda'))
  best_x=None
  best_y=1e10
  for idx in range(nBins**nDeaths):
    y=mean[idx][0]-ucb_mult*stdev[idx][0]
    if y<best_y:
      best_x=itol(idx,[nBins]*nDeaths)
      best_y=y
  best_x = [bins[i] for i in best_x]
  for i in range(nDeaths):
    points.append([dates[caseI+nCases-nDeaths+i],best_x[i]])
with open('points2.csv','w') as fi:
  csv.writer(fi).writerows(points)

