from pix2tex.dataset.dataset import Im2LatexDataset
import os
import argparse
import logging
import yaml

import torch
from munch import Munch
from tqdm.auto import tqdm
import wandb
import torch.nn as nn
from pix2tex.eval import evaluate
from pix2tex.models import get_model
# from pix2tex.utils import *
from pix2tex.utils import in_model_path, parse_args, seed_everything, get_optimizer, get_scheduler


def data_parallel(module, inputs, device_ids, output_device=None, **kwargs):
    if not device_ids or len(device_ids) == 1:
        return module(inputs, **kwargs)
    if output_device is None:
        output_device = device_ids[0]
    replicas = nn.parallel.replicate(module, device_ids)
    inputs = nn.parallel.scatter(inputs, device_ids)  # Slices tensors into approximately equal chunks and distributes them across given GPUs.
    kwargs = nn.parallel.scatter(kwargs, device_ids)  # Duplicates references to objects that are not tensors.
    replicas = replicas[:len(inputs)]
    kwargs = kwargs[:len(inputs)]
    outputs = nn.parallel.parallel_apply(replicas, inputs, kwargs)
    return nn.parallel.gather(outputs, output_device)


def gpu_memory_check(model, args):
    # check if largest batch can be handled by system
    try:
        batchsize = args.batchsize if args.get('micro_batchsize', -1) == -1 else args.micro_batchsize
        for _ in range(5):
            im = torch.empty(batchsize, args.channels, args.max_height, args.min_height, device=args.device).float()
            seq = torch.randint(0, args.num_tokens, (batchsize, args.max_seq_len), device=args.device).long()
            # model.decoder(seq, context=model.encoder(im)).sum().backward()
            encoded = data_parallel(model.encoder, inputs=im, device_ids=args.gpu_devices)
            loss = data_parallel(model.decoder, inputs=seq, device_ids=args.gpu_devices, context=encoded)
            loss.sum().backward()
    except RuntimeError:
        raise RuntimeError("The system cannot handle a batch size of %i for the maximum image size (%i, %i). Try to use a smaller micro batchsize." % (batchsize, args.max_height, args.max_width))
    model.zero_grad()
    torch.cuda.empty_cache()
    del im, seq


def train(args):
    dataloader = Im2LatexDataset().load(args.data)
    dataloader.update(**args, test=False)
    valdataloader = Im2LatexDataset().load(args.valdata)
    valargs = args.copy()
    valargs.update(batchsize=args.testbatchsize, keep_smaller_batches=True, test=True)
    valdataloader.update(**valargs)
    device = args.device
    model = get_model(args)
    gpu_memory_check(model, args)
    if args.load_chkpt is not None:
        model.load_state_dict(torch.load(args.load_chkpt, map_location=device))
    encoder, decoder = model.encoder, model.decoder
    max_bleu, max_token_acc = 0, 0
    out_path = os.path.join(args.model_path, args.name)
    os.makedirs(out_path, exist_ok=True)

    def save_models(e, step=0):
        torch.save(model.state_dict(), os.path.join(out_path, '%s_e%02d_step%02d.pth' % (args.name, e+1, step)))
        yaml.dump(dict(args), open(os.path.join(out_path, 'config.yaml'), 'w+'))

    opt = get_optimizer(args.optimizer)(model.parameters(), args.lr, betas=args.betas)
    scheduler = get_scheduler(args.scheduler)(opt, step_size=args.lr_step, gamma=args.gamma)

    microbatch = args.get('micro_batchsize', -1)
    if microbatch == -1:
        microbatch = args.batchsize

    try:
        for e in range(args.epoch, args.epochs):
            args.epoch = e
            dset = tqdm(iter(dataloader))
            for i, (seq, im) in enumerate(dset):
                if seq is not None and im is not None:
                    opt.zero_grad()
                    total_loss = 0
                    for j in range(0, len(im), microbatch):
                        tgt_seq, tgt_mask = seq['input_ids'][j:j+microbatch].to(device), seq['attention_mask'][j:j+microbatch].bool().to(device)
                        # encoded = encoder(im[j:j+microbatch].to(device))
                        encoded = data_parallel(encoder, inputs=im[j:j+microbatch].to(device), device_ids=args.gpu_devices)
                        # loss = decoder(tgt_seq, mask=tgt_mask, context=encoded)*microbatch/args.batchsize
                        loss = data_parallel(module=decoder, inputs=tgt_seq, device_ids=args.gpu_devices, mask=tgt_mask, context=encoded)*microbatch/args.batchsize
                        # loss.backward()
                        loss.mean().backward()  # data parallism loss is a vector
                        total_loss += loss.mean().item()
                        torch.nn.utils.clip_grad_norm_(model.parameters(), 1)
                    opt.step()
                    scheduler.step()
                    dset.set_description('Loss: %.4f' % total_loss)
                    if args.wandb:
                        wandb.log({'train/loss': total_loss})
                if (i+1+len(dataloader)*e) % args.sample_freq == 0:
                    bleu_score, edit_distance, token_accuracy = evaluate(model, valdataloader, args, num_batches=int(args.valbatches*e/args.epochs), name='val')
                    if bleu_score > max_bleu and token_accuracy > max_token_acc:
                        max_bleu, max_token_acc = bleu_score, token_accuracy
                        save_models(e, step=i)
            if (e+1) % args.save_freq == 0:
                save_models(e, step=len(dataloader))
            if args.wandb:
                wandb.log({'train/epoch': e+1})
    except KeyboardInterrupt:
        if e >= 2:
            save_models(e)
        raise KeyboardInterrupt
    save_models(e)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Train model')
    parser.add_argument('--config', default=None, help='path to yaml config file', type=str)
    parser.add_argument('--no_cuda', action='store_true', help='Use CPU')
    parser.add_argument('--debug', action='store_true', help='DEBUG')
    parser.add_argument('--resume', help='path to checkpoint folder', action='store_true')
    parsed_args = parser.parse_args()
    if parsed_args.config is None:
        with in_model_path():
            parsed_args.config = os.path.realpath('settings/debug.yaml')
    with open(parsed_args.config, 'r') as f:
        params = yaml.load(f, Loader=yaml.FullLoader)
    args = parse_args(Munch(params), **vars(parsed_args))
    logging.getLogger().setLevel(logging.DEBUG if parsed_args.debug else logging.WARNING)
    seed_everything(args.seed)
    if args.wandb:
        if not parsed_args.resume:
            args.id = wandb.util.generate_id()
        wandb.init(config=dict(args), resume='allow', name=args.name, id=args.id)
    train(args)
