import cv2
import pandas as pd
from PIL import ImageGrab
from PIL import Image
import os
import sys
import argparse
import logging
import yaml

import numpy as np
import torch
from torchvision import transforms
from munch import Munch
from transformers import PreTrainedTokenizerFast

from dataset.dataset import Im2LatexDataset
from models import get_model
from utils import *


def main(arguments):

    with open(arguments.config, 'r') as f:
        params = yaml.load(f, Loader=yaml.FullLoader)
    args = Munch(params)
    args.update(**vars(arguments))
    args.wandb = False
    args.device = 'cuda' if torch.cuda.is_available() and not args.no_cuda else 'cpu'

    model = get_model(args)
    model.load_state_dict(torch.load(args.checkpoint))
    model.to(args.device)
    encoder, decoder = model.encoder, model.decoder
    transform = transforms.Compose([transforms.PILToTensor()])
    tokenizer = PreTrainedTokenizerFast(tokenizer_file=args.tokenizer)
    img = ImageGrab.grabclipboard()
    if img is None:
        raise ValueError('copy an imagae into the clipboard.')
    ratios = [a/b for a, b in zip(img.size, args.max_dimensions)]
    if any([r > 1 for r in ratios]):
        size = np.array(img.size)//max(ratios)
        img = img.resize(size.astype(int))
    t = transform(pad(img, args.patch_size)).unsqueeze(0)/255
    im = t.to(args.device)

    with torch.no_grad():
        model.eval()
        device = args.device
        encoded = encoder(im.to(device))
        dec = decoder.generate(torch.LongTensor([args.bos_token])[:, None].to(device), args.max_seq_len,
                               eos_token=args.eos_token, context=encoded.detach(), temperature=args.temperature)
        pred = post_process(token2str(dec, tokenizer)[0])
    print(pred)
    df = pd.DataFrame([pred])
    df.to_clipboard(index=False, header=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Use model', add_help=False)
    parser.add_argument('-t', '--temperature', type=float, default=.4, help='Softmax sampling frequency')
    parser.add_argument('-c', '--config', type=str, default='D:/ML/pix2tex/checkpoints/hybrid/config.yaml')
    parser.add_argument('-m', '--checkpoint', type=str, default='D:/ML/pix2tex/checkpoints/hybrid/pix2tex_cont2_e15.pth')
    parser.add_argument('--no-cuda', action='store_true', help='Compute on CPU')
    args = parser.parse_args()
    main(args)
