import os
import sys
import argparse
import logging
import yaml

import numpy as np
import torch
from torchtext.data import metrics
from munch import Munch
from tqdm.auto import tqdm
import wandb

from dataset.dataset import Im2LatexDataset
from models import get_model
from utils import *


def detokenize(tokens, tokenizer):
    toks = [tokenizer.convert_ids_to_tokens(tok) for tok in tokens]
    for b in range(len(toks)):
        for i in reversed(range(len(toks[b]))):
            toks[b][i] = toks[b][i].replace('Ġ', ' ').strip()
            if toks[b][i] in (['[BOS]', '[EOS]', '[PAD]']):
                del toks[b][i]
    return toks


@torch.no_grad()
def evaluate(model: torch.nn.Module, dataset: Im2LatexDataset, args: Munch, name: str = 'test'):
    """evaluates the model. Returns bleu score on the dataset

    Args:
        model (torch.nn.Module): the model
        dataset (Im2LatexDataset): test dataset
        args (Munch): arguments
        name (str, optional): name of the test e.g. val or test for wandb. Defaults to 'test'.

    Returns:
        bleu_score: BLEU score of validation set.
    """
    assert len(dataset) > 0
    device = args.device
    bleus = []
    pbar = tqdm(enumerate(iter(dataset)), total=len(dataset))
    for i, (seq, im) in pbar:
        tgt_seq, tgt_mask = seq['input_ids'].to(device), seq['attention_mask'].bool().to(device)
        encoded = model.encoder(im.to(device))
        #loss = decoder(tgt_seq, mask=tgt_mask, context=encoded)
        dec = model.decoder.generate(torch.LongTensor([args.bos_token]*len(encoded))[:, None].to(device), args.max_seq_len,
                                     eos_token=args.pad_token, context=encoded)
        pred = detokenize(dec, dataset.tokenizer)
        truth = detokenize(seq['input_ids'], dataset.tokenizer)
        bleus.append(metrics.bleu_score(pred, [alternatives(x) for x in truth]))
        pbar.set_description('BLEU: %.2f' % (np.mean(bleus)))
    bleu_score = np.mean(bleus)
    # samples
    pred = token2str(dec, dataset.tokenizer)
    truth = token2str(seq['input_ids'], dataset.tokenizer)
    if args.wandb:
        table = wandb.Table(columns=["Truth", "Prediction"])
        for k in range(min([len(pred), args.test_samples])):
            table.add_data(post_process(truth[k]), post_process(pred[k]))
        wandb.log({name+'/examples': table, name+'/bleu': bleu_score})
    else:
        print('\n%s\n%s' % (truth, pred))
        print('BLEU: %.2f' % bleu_score)
    return bleu_score


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Test model')
    parser.add_argument('--config', default='settings/default.yaml', help='path to yaml config file', type=argparse.FileType('r'))
    parser.add_argument('-c', '--checkpoint', default=None, type=str, help='path to model checkpoint')
    parser.add_argument('-d', '--data', default='dataset/data/val.pkl', type=str, help='Path to Dataset pkl file')
    parser.add_argument('--no-cuda', action='store_true', help='Use CPU')
    parser.add_argument('-b', '--batchsize', type=int, default=None, help='Batch size')
    parser.add_argument('--debug', action='store_true', help='DEBUG')

    parsed_args = parser.parse_args()
    with parsed_args.config as f:
        params = yaml.load(f, Loader=yaml.FullLoader)
    args = parse_args(Munch(params))
    if parsed_args.batchsize is not None:
        args.testbatchsize = parsed_args.batchsize
    args.wandb = False
    logging.getLogger().setLevel(logging.DEBUG if parsed_args.debug else logging.WARNING)
    seed_everything(args.seed)
    model = get_model(args)
    if parsed_args.checkpoint is not None:
        model.load_state_dict(torch.load(parsed_args.checkpoint, args.device))
    dataset = Im2LatexDataset().load(parsed_args.data)
    valargs = args.copy()
    valargs.update(batchsize=args.testbatchsize, keep_smaller_batches=True)
    dataset.update(**valargs)
    evaluate(model, dataset, args)
