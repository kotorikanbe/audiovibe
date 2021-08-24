import sys
sys.path.append('..')

import argparse

def _base_arg_parser():
    p = argparse.ArgumentParser()
    p.add_argument('--audio', type=str)
    p.add_argument('--task', type=str, default='run', choices=['run', 'build', 'play'])
    p.add_argument('--len-hop', type=int, default=512)
    p.add_argument('--data-dir', type=str, default='.')

    p.add_argument('--plot', action='store_true')
    return p

def tune_beat_parser(base_parser=None):
    if base_parser is None:
        p = _base_arg_parser()

    p.add_argument('--len-frame', type=int, default=300)
    p.add_argument('--min-tempo', type=int, default=150)
    p.add_argument('--max-tempo', type=int, default=400)

    return p

def tune_pitch_parser(base_parser=None):
    if base_parser is None:
        p = _base_arg_parser()
    
    p.add_argument('--pitch', action='store_true')
    p.add_argument('--pitch-alg', type=str, default='pyin', choices=['pyin', 'yin'])
    p.add_argument('--chroma', action='store_true')
    p.add_argument('--chroma-alg', type=str, default='stft', choices=['stft', 'cqt'])
    p.add_argument('--len-window', type=int, default=2048)
    p.add_argument('--fmin', type=str, default='C2')
    p.add_argument('--fmax', type=str, default='C7')
    p.add_argument('--yin-thres', type=float, default=0.8)

    return p

from vib_music import LibrosaContext
from vib_music import PlotContext
from vib_music import MotorInvoker
from vib_music import AudioProcess, MotorProcess, BoardProcess

def _main(opt, librosa_cfg=None, invoker_cfg=None, plot_cfg=None):
    if opt.task == 'run' or opt.task == 'build':
        ctx = LibrosaContext.from_config(librosa_cfg)
        ctx.save_features(root=opt.data_dir)

    if opt.plot and plot_cfg is not None:
        ctx = PlotContext(**plot_cfg)
        ctx.save_plots()

    if opt.task == 'run' or opt.task == 'play':
        invoker = MotorInvoker.from_config(invoker_cfg)

        print('Init Processes...')
        audio_proc = AudioProcess(opt.audio, opt.len_hop)
        motor_proc = MotorProcess(invoker)
        board_proc = BoardProcess()

        motor_proc.attach(audio_proc)
        board_proc.attach(audio_proc, motor_proc)

        print('Start To Run...')
        board_proc.start()
        motor_proc.start()
        audio_proc.start()

        audio_proc.join()
        motor_proc.join()
        board_proc.join()