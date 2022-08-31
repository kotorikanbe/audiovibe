import numpy as np
from runutils import tune_rmse_parser
from runutils import _main
import sys
from vib_music import FeatureManager
from vib_music.misc import init_vibration_extraction_config

@FeatureManager.vibration_mode(over_ride=False)
def rmse_voltage(fm:FeatureManager, scale=150) -> np.ndarray:
    rmse = fm.feature_data('rmse')

    rmse = (rmse-rmse.min()) / (rmse.max()-rmse.min())
    rmse  = rmse ** 2

    print("the scale is %d" % (scale))

    bins = np.linspace(0., 1., scale, endpoint=True)
    level = np.digitize(rmse, bins).astype(np.uint8)

    # mimic a square wave for each frame [x, x, x, x, 0, 0, 0, 0]
    # [x,x,x,x,0,0,0,0,x,x,x,x,0,0,0,0,x,x,x,x,0,0,0,0] - 300Hz

    # when using 2D sequence, do not use plot function
    level_zeros = np.zeros_like(level)
    level_seq = np.stack([level]*4+[level_zeros]*4, axis=-1)
    level_seq = np.concatenate([level_seq]*3, axis=-1)

    return level_seq


def main():
    p = tune_rmse_parser()
    opt = p.parse_args()
    print(opt)

    librosa_config = None
    plot_config = None
    if opt.task == 'run' or 'build':
        print('Buidling Feature Database...', end='')
        librosa_config = init_vibration_extraction_config()
        librosa_config['audio'] = opt.audio
        librosa_config['len_hop'] = 512
        librosa_config['stgs']['rmse'] = {
            'len_window': 2048,
        }

    if opt.plot:
        plot_config = {
            'plots': ['waveform', 'wavermse', 'vibration_adc']
        }

    vib_kwargs_dict = {"scale":100}
    _main(opt, 'rmse_voltage', 'adc', librosa_config, plot_config, vib_kwargs_dict)


# debug part
sys.argv = ["rmse.py", "--audio", "../audio/kick.wav", "--task", "run"]
print("DEBUGDEBUGDEBUGDEBUG...")
###

main()