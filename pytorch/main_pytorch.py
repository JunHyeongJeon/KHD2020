
import os, sys
import argparse
import time
import random
import cv2
import numpy as np
import torch
import torch.nn as nn
from torchvision.models import resnet18, resnet34
#import torchvision.transforms as transforms
from torch.utils.data import Dataset, DataLoader, TensorDataset, random_split

import nsml
from nsml.constants import DATASET_PATH, GPU_NUM

from torch.utils.data import Dataset, DataLoader

from PIL import Image
from collections import defaultdict
from sklearn.model_selection import train_test_split
from sklearn.metrics import f1_score

from efficientnet_pytorch import EfficientNet

import argparse
from random import uniform
from imgaug import augmenters as iaa



IMSIZE = 120, 60
VAL_RATIO = 0.2

# Seed
RANDOM_SEED = 44
torch.manual_seed(RANDOM_SEED)
torch.cuda.manual_seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)
random.seed(RANDOM_SEED)

class AverageMeter(object):
  """Computes and stores the average and current value"""
  def __init__(self):
      self.reset()

  def reset(self):
    self.val = 0
    self.avg = 0
    self.sum = 0
    self.count = 0

  def update(self, val, n=1):
    self.val = val
    self.sum += val * n
    self.count += n
    self.avg = self.sum / self.count


def bind_model(model, args):
    def save(dir_name):
        os.makedirs(dir_name, exist_ok=True)
        torch.save(model.state_dict(), os.path.join(dir_name, 'model'))
        print('model saved!')

    def load(dir_name):
        model.load_state_dict(torch.load(os.path.join(dir_name, 'model')))
        model.eval()
        print('model loaded!')

    def infer(data):  ## test mode
        X = ImagePreprocessing(data, args)
        X = np.array(X)
        X = np.expand_dims(X, axis=1)
        ##### DO NOT CHANGE ORDER OF TEST DATA #####

        #b c h w
        with torch.no_grad():
            X = torch.from_numpy(X).float().to(device)
            pred = model.forward(X)
            prob, pred_cls = torch.max(pred, 1)
            pred_cls = pred_cls.tolist()
            #pred_cls = pred_cls.data.cpu().numpy()
        print('Prediction done!\n Saving the result...')
        return pred_cls

    nsml.bind(save=save, load=load, infer=infer)

def DataLoad(imdir):
    impath = [os.path.join(dirpath, f) for dirpath, dirnames, files in os.walk(imdir) for f in files if all(s in f for s in ['.jpg'])]

    img_list = defaultdict(list)
    print('Loading', len(impath), 'images ...')

    for i, p in enumerate(impath):
        img_whole = cv2.imread(p, 0)
        h, w = img_whole.shape
        h_, w_ = h, w//2
        l_img = img_whole[:, w_:2*w_]
        r_img = img_whole[:, :w_]

        _, l_cls, r_cls = os.path.basename(p).split('.')[0].split('_')

        if l_cls=='0' or l_cls=='1' or l_cls=='2' or l_cls=='3':
            img_list[int(l_cls)].append(l_img)
        if r_cls=='0' or r_cls=='1' or r_cls=='2' or r_cls=='3':
            img_list[int(r_cls)].append(r_img)

    img_train,img_val = [],[]
    lb_train,lb_val = [],[]


    for i in [1,0,2,3]:
        timg, vimg, tlabel, vlabel = train_test_split(img_list[i],[i]*len(img_list[i]),test_size=0.2,shuffle=True,random_state=13241)

        if i == 1:
            num = len(timg)
        if i == 0:
            # downsample class 0, upsample class 2,3
            timg = random.sample(timg, num)
            tlabel = [0] * num
        if i == 2 or i == 3:
            class_remain = (num - len(timg)) % len(timg)
            class_quot = int((num - len(timg)) / len(timg))
            timg += timg * class_quot
            timg += random.sample(timg, class_remain)
            tlabel = [i] * num

        # Down-sampling
        # if i == 0:
        #     timg = timg[:400]
        #     tlabel = tlabel[:400]
        timg_flip = [cv2.flip(img, 1) for img in timg]
        timg += timg_flip
        tlabel = tlabel * 2
        print("trian class",i,len(timg))
        img_train += timg
        img_val += vimg
        lb_train += tlabel
        lb_val += vlabel

    print(len(img_train), 'Train data with label 0-3 loaded!')
    print(len(img_val), 'Validation data with label 0-3 loaded!')

    return img_train,lb_train,img_val,lb_val


def DataLoadDebugging(imdir):
    impath = [os.path.join(dirpath, f) for dirpath, dirnames, files in os.walk(imdir) for f in files if
              all(s in f for s in ['.jpg'])]

    img_list = defaultdict(list)

    print('Loading', len(impath), 'images ...')

    left_cnts = [0, 0, 0, 0]
    right_cnts = [0, 0, 0, 0]
    for i, p in enumerate(impath):
        img_whole = cv2.imread(p, 0)
        # zero padding
        img_whole = image_padding(img_whole)
        h, w = img_whole.shape
        h_, w_ = h, w // 2
        l_img = img_whole[:, :w_]
        r_img = img_whole[:, w_:2 * w_]
        r_img = cv2.flip(r_img, 1)  # Flip Right Image to Left

        _, l_cls, r_cls = os.path.basename(p).split('.')[0].split('_')

        if l_cls == '0' or l_cls == '1' or l_cls == '2' or l_cls == '3':
            img_list[int(l_cls)].append(l_img)
            left_cnts[int(l_cls)] += 1
        if r_cls == '0' or r_cls == '1' or r_cls == '2' or r_cls == '3':
            img_list[int(r_cls)].append(r_img)
            right_cnts[int(r_cls)] += 1

    img_check = [0,0,0,0]
    for p in impath:
        img_whole = cv2.imread(p, 0)
        _, l_cls, r_cls = os.path.basename(p).split('.')[0].split('_')
        if (str(l_cls) == '0' or str(r_cls) == '0') and img_check[0] == 0:
            img_check[0] = 1
            print(list(img_whole))
            print("Left label : %s | Right label : %s\n" % (l_cls, r_cls))
        elif (str(l_cls) == '1' or str(r_cls) == '1')  and img_check[1] == 0:
            img_check[1] = 1
            print(list(img_whole))
            print("Left label : %s | Right label : %s\n" % (l_cls, r_cls))
        elif (str(l_cls) == '2' or str(r_cls) == '2')  and img_check[2] == 0:
            img_check[2] = 1
            print(list(img_whole))
            print("Left label : %s | Right label : %s\n" % (l_cls, r_cls))
        elif (str(l_cls) == '3' or str(r_cls) == '3')  and img_check[3] == 0:
            img_check[3] = 1
            print(list(img_whole))
            print("Left label : %s | Right label : %s\n" % (l_cls, r_cls))

    print("Left class :", left_cnts)
    print("Right class :", right_cnts)
    exit(0)
    img_train, img_val = [], []
    lb_train, lb_val = [], []

    for i in range(0, 4):
        timg, vimg, tlabel, vlabel = train_test_split(img_list[i], [i] * len(img_list[i]), test_size=0.2, shuffle=True,
                                                      random_state=13241)

        # Down-sampling
        if i == 0:
            timg = timg[:400]
            tlabel = tlabel[:400]

        img_train += timg
        img_val += vimg
        lb_train += tlabel
        lb_val += vlabel

    print(len(img_train), 'Train data with label 0-3 loaded!')
    print(len(img_val), 'Validation data with label 0-3 loaded!')

    return img_train, lb_train, img_val, lb_val

def image_padding(img_whole):
    img = np.zeros((600,300))
    h, w = img_whole.shape

    if (600 - h) != 0:
        gap = int((600 - h)/2)
        img[gap:gap+h,:] = img_whole
    elif (300 - w) != 0:
        gap = int((300 - w)/2)
        img[:,gap:gap+w] = img_whole
    else:
        img = img_whole

    return img

def image_windowing(img, w_min=50, w_max=180):
    img_w = img.copy()

    img_w[img_w < w_min] = w_min
    img_w[img_w > w_max] = w_max

    return img_w

def image_bg_reduction(img):
    img_wo_bg = img.copy()

    img_wo_bg[:250] = 0
    img_wo_bg[500:] = 0
    img_wo_bg[:, :60] = 0
    img_wo_bg[:, -60:] = 0

    return img_wo_bg

def image_roi_crop(img, img_size):
    half_size = img_size // 2
    return img[350-half_size:350+half_size,
               150-half_size:150+half_size].copy()

def image_minmax(img, min=50, max=180):
    img_minmax = ((img - np.min(img)) / (np.max(img) - np.min(img))).copy()
    img_minmax[img_minmax < 0] = 0
    img_minmax[img_minmax > 1] = 1
    return img_minmax

def ImagePreprocessing(img, args):
    # 자유롭게 작성
    print('Preprocessing ...')
    for i, im, in enumerate(img):
        # Zero-padding
        im = image_padding(im)
        # Windowing
        im = image_windowing(im, args.w_min, args.w_max)
        # Background reduction
        im = image_bg_reduction(im)
        # RoI crop
        im = image_roi_crop(im, args.img_size)
        # Min-Max scaling
        im = image_minmax(im, args.w_min, args.w_max)

        img[i] = im
    print(len(img), 'images processed!')
    return img


class Sdataset(Dataset):
    def __init__(self, images, labels, args, augmentation):
        self.images = images
        self.args = args
        self._init_images()
        self.labels = labels
        self.augmentation = augmentation

        print("images:", len((self.images)), "#labels:", len((self.labels)))

    def _init_images(self):
        self.images = ImagePreprocessing(self.images, self.args)
        self.images = np.array(self.images)
        self.images = np.expand_dims(self.images, axis=1)

    def augment_img(self, img):
        scale_factor = uniform(1-self.args.scale_factor, 1+self.args.scale_factor)
        rot_factor = uniform(-self.args.rot_factor, self.args.rot_factor)

        seq = iaa.Sequential([
                iaa.Affine(
                    scale=(scale_factor, scale_factor),
                    rotate=rot_factor
                )
            ])

        seq_det = seq.to_deterministic()
        img = seq_det.augment_images(img)

        return img

    def __getitem__(self, index):
        image = self.images[index]
        label = self.labels[index]

        if self.augmentation:
            image = self.augment_img(image)

        image = torch.tensor(image).float()

        return image, label

    def __len__(self):
        return len(self.labels)

def get_current_lr(optimizer):
    return optimizer.state_dict()['param_groups'][0]['lr']

def lr_update(epoch, args, optimizer):
    prev_lr = get_current_lr(optimizer)
    if (epoch + 1) in args.lr_decay_epoch:
        for param_group in optimizer.param_groups:
            param_group['lr'] = (prev_lr * 0.1)
            print("LR Decay : %.7f to %.7f" % (prev_lr, prev_lr * 0.1))

def ParserArguments():
    args = argparse.ArgumentParser()

    # Setting Hyperparameters
    args.add_argument('--nb_epoch', type=int, default=30)          # epoch 수 설정
    args.add_argument('--batch_size', type=int, default=32)      # batch size 설정
    args.add_argument('--learning_rate', type=float, default=5e-3)  # learning rate 설정
    args.add_argument('--wd', type=float, default=3e-4)  # learning rate 설정
    args.add_argument('--lr_decay_epoch', type=str, default='20,25')  # learning rate 설정
    args.add_argument('--num_classes', type=int, default=4)     # 분류될 클래스 수는 4개
    args.add_argument('--img_size', type=int, default=224)
    args.add_argument('--w_min', type=int, default=50)
    args.add_argument('--w_max', type=int, default=180)

    # Network
    args.add_argument('--network', type=str, default='efficientnet-b4')
    args.add_argument('--resume', type=str, default='weights/efficient-b4.pth')          
    args.add_argument('--dropout', type=float, default=0.5)

    # Augmentation
    args.add_argument('--x_trans_factor', type=float, default=0.15)
    args.add_argument('--y_trans_factor', type=float, default=0.15)
    args.add_argument('--rot_factor', type=float, default=30)          
    args.add_argument('--scale_factor', type=float, default=0.15)          

    # DO NOT CHANGE (for nsml)
    args.add_argument('--mode', type=str, default='train', help='submit일 때 test로 설정됩니다.')
    args.add_argument('--iteration', type=str, default='0',
                      help='fork 명령어를 입력할때의 체크포인트로 설정됩니다. 체크포인트 옵션을 안주면 마지막 wall time 의 model 을 가져옵니다.')
    args.add_argument('--pause', type=int, default=0, help='model 을 load 할때 1로 설정됩니다.')

    args = args.parse_args()
    args.lr_decay_epoch = map(float, args.lr_decay_epoch.split(','))

    return args

if __name__ == '__main__':
    print(GPU_NUM)
    args = ParserArguments()

    device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')

    #####   Model   #####
    if 'efficientnet' in args.network:
        model = EfficientNet.from_name(args.network)
        model._change_in_channels(1)
        model._fc = nn.Linear(model._fc.in_features, args.num_classes)
    elif args.network == 'resnet18':
        model = resnet18(pretrained=False)
        model.conv1 = nn.Conv2d(1, model.conv1.out_channels, kernel_size=7, stride=2, padding=3,
                               bias=False)
        model.fc = nn.Linear(model.fc.in_features, args.num_classes)
    elif args.network == 'resnet34':
        model = resnet34(pretrained=False)
        model.conv1 = nn.Conv2d(1, model.conv1.out_channels, kernel_size=7, stride=2, padding=3,
                               bias=False)
        #model.fc = nn.Linear(model.fc.in_features, args.num_classes)
        model.fc = nn.Sequential(
            nn.Dropout(p=args.dropout),
            nn.Linear(model.fc.in_features, args.num_classes)
        )

    model.to(device)
    # class_weights = torch.Tensor([1/0.78, 1/0.13, 1/0.06, 1/0.03])
    #class_weights = torch.Tensor([1,2,5,10])
    #criterion = nn.CrossEntropyLoss(class_weights).to(device)
    criterion = nn.CrossEntropyLoss().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate, weight_decay=args.wd)

    bind_model(model, args)

    if args.pause:  ## for test mode
        print('Inferring Start ...')
        nsml.paused(scope=locals())

    if args.mode == 'train':  ## for train mode
        print('Training start ...')
        # 자유롭게 작성
        timages, tlabels, vimages, vlabels = DataLoad(imdir=os.path.join(DATASET_PATH, 'train'))
        tr_set = Sdataset(timages, tlabels, args, True)
        val_set = Sdataset(vimages, vlabels, args, False)
        batch_train = DataLoader(tr_set, batch_size=args.batch_size, shuffle=True)
        batch_val = DataLoader(val_set, batch_size=args.batch_size, shuffle=False)

        #####   Training loop   #####
        STEP_SIZE_TRAIN = len(timages) // args.batch_size
        print('\n\n STEP_SIZE_TRAIN= {}\n\n'.format(STEP_SIZE_TRAIN))
        t0 = time.time()

        for epoch in range(args.nb_epoch):
            t1 = time.time()
            print('Model fitting ...')
            print('epoch = {} / {}'.format(epoch + 1, args.nb_epoch))
            print('check point = {}'.format(epoch))

            ## Training
            true_labels = []
            pred_labels = []
            train_loss = AverageMeter()
            a, a_val, tp, tp_val = 0, 0, 0, 0
            for i, (x_tr, y_tr) in enumerate(batch_train):
                x_tr, y_tr = x_tr.to(device), y_tr.to(device)
                optimizer.zero_grad()
                pred = model(x_tr)
                loss = criterion(pred, y_tr)
                loss.backward()
                optimizer.step()
                prob, pred_cls = torch.max(pred, 1)
                a += y_tr.size(0)
                tp += (pred_cls == y_tr).sum().item()

                train_loss.update(loss.item(), len(x_tr))
                true_labels.extend(list(y_tr.cpu().numpy().astype(int)))
                pred_labels.extend(list(pred_cls.cpu().numpy().astype(int)))

                if i%10 == 0:
                    print("  * Iter Loss [{:d}/{:d}] loss = {}".format(i+1, len(batch_train), train_loss.avg))

            # train performance
            acc = tp / a
            class0_f1, class1_f1, class2_f1, class3_f1 = f1_score(true_labels, pred_labels, average=None)
            train_weighted_f1 = (class0_f1 + class1_f1*2 + class2_f1*3 + class3_f1*4) / 10.
            print("  * Train Class1 F1= {:.2f} | Class2 F1 = {:.2f} | Class3 F1 = {:.2f} | Class4 F1 = {:.2f} | Weighted F1 = {:.2f}"\
                   .format(class0_f1, class1_f1, class2_f1, class3_f1, train_weighted_f1))

            ## Validation
            val_loss = AverageMeter()
            true_labels = []
            pred_labels = []
            with torch.no_grad():
                for j, (x_val, y_val) in enumerate(batch_val):
                    x_val, y_val = x_val.to(device), y_val.to(device)

                    pred_val = model(x_val)
                    loss_val = criterion(pred_val, y_val)
                    prob_val, pred_cls_val = torch.max(pred_val, 1)
                    a_val += y_val.size(0)
                    tp_val += (pred_cls_val == y_val).sum().item()

                    val_loss.update(loss_val.item(), len(x_val))
                    true_labels.extend(list(y_val.cpu().numpy().astype(int)))
                    pred_labels.extend(list(pred_cls_val.cpu().numpy().astype(int)))

            # validation performance
            acc_val = tp_val / a_val
            class0_f1, class1_f1, class2_f1, class3_f1 = f1_score(true_labels, pred_labels, average=None)
            val_weighted_f1 = (class0_f1 + class1_f1*2 + class2_f1*3 + class3_f1*4) / 10.
            print("  * Valid Class1 F1= {:.2f} | Class2 F1 = {:.2f} | Class3 F1 = {:.2f} | Class4 F1 = {:.2f} | Weighted F1 = {:.2f}"\
                   .format(class0_f1, class1_f1, class2_f1, class3_f1, val_weighted_f1))

            # total summary
            print("  * Train loss = {:.4f} | Train weighted F1 = {:.4f} | Val loss = {:.4f} | Val weighted F1 = {:.4f}"\
                    .format(train_loss.avg, train_weighted_f1, val_loss.avg, val_weighted_f1))
            nsml.report(summary=True, step=epoch, epoch_total=args.nb_epoch,
                        loss=train_loss.avg, f1=train_weighted_f1, val_loss=val_loss.avg, val_f1=val_weighted_f1)
            nsml.save(epoch)
            print('Training time for one epoch : %.1f\n' % (time.time() - t1))

            # f1 score per class
            # acc per class
            lr_update(epoch, args, optimizer)
        print('Total training time : %.1f' % (time.time() - t0))
