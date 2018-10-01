import torch
import torch.nn as nn
import torch.optim as optim
import torch.optim.lr_scheduler as lr_scheduler

import math, random, sys
from optparse import OptionParser
from collections import deque

from mpn import *

parser = OptionParser()
parser.add_option("-t", "--train", dest="train_path")
parser.add_option("-m", "--save_dir", dest="save_path")
parser.add_option("-b", "--batch", dest="batch_size", default=50)
parser.add_option("-w", "--hidden", dest="hidden_size", default=300)
parser.add_option("-d", "--depth", dest="depth", default=3)
parser.add_option("-e", "--epoch", dest="epoch", default=30)
parser.add_option("-p", "--dropout", dest="dropout", default=0)
parser.add_option("-g", "--seed", dest="seed", default=1)
parser.add_option("-x", "--metric", dest="metric", default='rmse')
parser.add_option("-a", "--act_func", dest="act_func", default='ReLU')
opts,args = parser.parse_args()
   
batch_size = int(opts.batch_size)
depth = int(opts.depth)
hidden_size = int(opts.hidden_size)
num_epoch = int(opts.epoch)
dropout = float(opts.dropout)
seed = int(opts.seed)

def get_data(path):
    data = []
    with open(path) as f:
        f.readline()
        for line in f:
            vals = line.strip("\r\n ").split(',')
            smiles = vals[0]
            vals = [float(x) for x in vals[1:]]
            data.append((smiles,vals))
    return data

data = get_data(opts.train_path)
random.seed(seed)
random.shuffle(data)
train_size,test_size = int(len(data) * 0.8), int(len(data) * 0.1)
train = data[ : train_size]
valid = data[train_size : train_size + test_size]
test = data[train_size + test_size : ]

num_tasks = len(data[0][1])
print "Number of tasks:", num_tasks

torch.manual_seed(1)
torch.cuda.manual_seed(1)

encoder = MPN(hidden_size, depth, dropout=dropout, act_func=opts.act_func)
model = nn.Sequential(
        encoder,
        nn.Linear(hidden_size, hidden_size), 
        nn.ReLU(), 
        nn.Linear(hidden_size, num_tasks)
    )
loss_fn = nn.MSELoss().cuda()
model = model.cuda()
print model

for param in model.parameters():
    if param.dim() == 1:
        nn.init.constant(param, 0)
    else:
        nn.init.xavier_normal(param)

optimizer = optim.Adam(model.parameters(), lr=1e-3)
scheduler = lr_scheduler.ExponentialLR(optimizer, 0.9)
scheduler.step()

def valid_loss(data):
    if opts.metric == 'mae':
        val_loss = nn.L1Loss(reduce=False)
    else:
        val_loss = nn.MSELoss(reduce=False)

    err = torch.zeros(num_tasks)
    model.train(False)
    for i in xrange(0, len(data), batch_size):
        batch = data[i:i+batch_size]
        mol_batch, label_batch = zip(*batch)
        mol_batch = mol2graph(mol_batch)
        labels = create_var(torch.Tensor(label_batch))

        preds = model(mol_batch)
        loss = val_loss(preds, labels)
        err += loss.data.sum(dim=0).cpu()

    model.train(True)
    err = err / len(data)
    if opts.metric == 'rmse':
        return err.sqrt().sum() / num_tasks
    else:
        return err.sum() / num_tasks
     
best_loss = 1e5
for epoch in xrange(num_epoch):
    mse,it = 0,0
    print "learning rate: %.6f" % scheduler.get_lr()[0]
    for i in xrange(0, len(train), batch_size):
        batch = train[i:i+batch_size]
        mol_batch, label_batch = zip(*batch)
        mol_batch = mol2graph(mol_batch)
        labels = create_var(torch.Tensor(label_batch))

        model.zero_grad()
        preds = model(mol_batch).view(-1)
        labels = labels.view(-1)
        loss = loss_fn(preds, labels)
        mse += loss.data[0] * batch_size 
        it += batch_size
        loss.backward()
        optimizer.step()

        if i % 1000 == 0:
            pnorm = math.sqrt(sum([p.norm().data[0] ** 2 for p in model.parameters()]))
            gnorm = math.sqrt(sum([p.grad.norm().data[0] ** 2 for p in model.parameters()]))
            print "RMSE=%.4f,PNorm=%.2f,GNorm=%.2f" % (math.sqrt(mse / it), pnorm, gnorm)
            sys.stdout.flush()
            mse,it = 0,0

    scheduler.step()
    cur_loss = valid_loss(valid)
    print "validation loss: %.4f" % cur_loss
    if opts.save_path is not None:
        torch.save(model.state_dict(), opts.save_path + "/model.iter-" + str(epoch))
        if cur_loss < best_loss:
            best_loss = cur_loss
            torch.save(model.state_dict(), opts.save_path + "/model.best")

model.load_state_dict(torch.load(opts.save_path + "/model.best"))
print "test loss: %.4f" % valid_loss(test)
