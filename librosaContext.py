import os
import pickle
import librosa
import numpy as np

def load_audio(sr):
    audio, sr = librosa.load('audio/YellowRiverSliced.wav', sr=sr)

    return audio, sr
# Strategy Pattern
class LibrosaContext(object):
    stg_meta_funcs = {}
    stg_funcs = {}
    def __init__(self, audio='', sr=None, stg=None):
        super().__init__()
        # load audio data
        if isinstance(audio, str):
            self.audio_name = os.path.basename(audio).split('.')[0]
            if len(audio) == 0:
                self.audio, self.sr = load_audio(sr=sr)
                self.audio = self.audio[:self.sr*3]
            else: 
                self.audio, self.sr = librosa.load(audio, sr=sr)
        else:
            assert isinstance(audio, np.ndarray), 'audio should be a path-like object or np.ndarray'
            assert sr is not None, 'SR cannot be None if audio is np.ndarray'
            self.audio_name = 'audio_clip'
            self.audio = audio
            self.sr = sr

        if isinstance(stg, str):
            self.stg_names = [stg]
            self.stg = [self._init_stg(stg)]
        elif isinstance(stg, list):
            self.stg_names = stg
            self.stg = [self._init_stg(s) for s in stg]
        elif isinstance(stg, dict):
            self.stg_names = list(stg.keys())
            self.stg = [self._init_stg(s, v) for s, v in stg.items()]
        else:
            self.stg_names = []
            self.stg = None
    
    def _init_stg(self, stg, kwargs=None):
        if stg in LibrosaContext.stg_funcs:
            return LibrosaContext.stg_funcs[stg]
        
        if kwargs is None:
            stg_name, *args = stg.split('_')
            kwargs = {}
        else:
            stg_name = stg
            args = []

        if stg_name in LibrosaContext.stg_meta_funcs:
            func = LibrosaContext.stg_meta_funcs[stg_name]
            def wfunc(autio, sr):
                return func(autio, sr, *args, **kwargs)
            wfunc.__name__ = stg
            return wfunc
        else:
            raise NotImplementedError(f'{stg} is not implemented')
    
    @property
    def sound(self):
        return self.audio
    
    @sound.setter
    def sound(self, sound):
        self.audio = sound

    @property
    def strategy(self):
        return self.stg

    @strategy.setter
    def strategy(self, stg):
        if isinstance(stg, str):
            self.stg_names = [stg]
            self.stg = [self._init_stg(stg)]
        elif isinstance(stg, list):
            self.stg_names = stg
            self.stg = [self._init_stg(s) for s in stg]
        else:
            self.stg_names = []
            self.stg = None

    def audio_features(self):
        if self.audio is None: return {}

        features = {'audio': self.audio.copy(), 'sr': self.sr}
        features.update({sname: func(self.audio, self.sr)
            for sname, func in zip(self.stg_names, self.stg)})
        return features
    
    def save_features(self, features=None):
        if features is None:
            features = self.audio_features()
        
        feat_dir = os.path.join('data', self.audio_name)
        os.makedirs(feat_dir, exist_ok=True)
        # save meta
        meta = {'audio_name': self.audio_name, 'sr': features['sr'],
            'len_sample': self.audio.shape[0]}
        meta['vibrations'] = self.stg_names
        with open(os.path.join(feat_dir, 'meta.pkl'), 'wb') as f:
            pickle.dump(meta, f)

        # save features
        for n in self.stg_names:
            with open(os.path.join(feat_dir, n+'.pkl'), 'wb') as f:
                pickle.dump(features[n], f)

    @classmethod
    def from_config(cls, config):
        #TODO: compability check
        assert config['version'] > 0.1

        audio = config['audio']
        sr = config['sr']

        # TODO: check args for each strategy
        stgs = config['stg']

        return cls(audio, sr, stgs)

def librosa_stg(func):
    if func.__name__ in LibrosaContext.stg_funcs:
        raise ValueError(f'Duplicate Function Name {func.__name__}')

    LibrosaContext.stg_funcs.update({func.__name__: func})
    return func

def librosa_stg_meta(func):
    if func.__name__ in LibrosaContext.stg_meta_funcs:
        raise ValueError(f'Duplicate Function Name {func.__name__}')

    LibrosaContext.stg_meta_funcs.update({func.__name__: func})
    return func

from config import HOP_LEN
from config import WIN_LEN
from config import FRAME_LEN # 300
@librosa_stg_meta
def beatplp(audio, sr, hop=HOP_LEN, len_frame=FRAME_LEN, tempo_min=30, tempo_max=300):
    hop = int(hop)
    len_frame = int(len_frame)

    # duration = hop * num_frame / sr
    onset_env = librosa.onset.onset_strength(y=audio, sr=sr)
    pulse = librosa.beat.plp(onset_envelope=onset_env, sr=sr,
        win_length=len_frame, tempo_min=tempo_min, tempo_max=tempo_max)
    ret = {
        'hop': hop, 'len_frame': len_frame,
        'tempo_min': tempo_min, 'tempo_max': tempo_max,
        'data': pulse
    }
    return ret

# @librosa_stg_meta
# def rmse(audio, sr, frame=WIN_LEN, hop=HOP_LEN):
#     frame = int(frame)
#     hop = int(hop)

#     # Do not pad the frame
#     return librosa.feature.rms(y=audio, frame_length=frame,
#         hop_length=hop, center=False)

# @librosa_stg
# def stempo(audio, sr):
#     onset_env = librosa.onset.onset_strength(audio, sr)
#     return librosa.beat.tempo(onset_envelope=onset_env, sr=sr)

# @librosa_stg
# def dtempo(audio, sr):
#     onset_env = librosa.onset.onset_strength(audio, sr)
#     return librosa.beat.tempo(onset_envelope=onset_env, sr=sr,
#         aggregate=None)

# @librosa_stg_meta
# def gramtempo(audio, sr, hop=512):
#     hop = int(hop)
#     onset_env = librosa.onset.onset_strength(audio, sr)
#     return librosa.feature.tempogram(onset_envelope=onset_env, sr=sr,
#         hop_length=hop, center=False)

# @librosa_stg_meta
# def pitchyin(audio, sr, frame=WIN_LEN, hop=HOP_LEN, thres=0.8):
#     frame = int(frame)
#     hop = int(hop)
#     thres = float(thres)

#     fmin = librosa.note_to_hz('C2')
#     fmax = librosa.note_to_hz('C7')

#     return librosa.yin(audio, fmin=fmin, fmax=fmax, sr=sr,
#         frame_length=frame, hop_length=hop, trough_threshold=thres, center=False)

# @librosa_stg_meta
# def pitchpyin(audio, sr, frame=WIN_LEN, hop=HOP_LEN):
#     frame = int(frame)
#     hop = int(hop)

#     fmin = librosa.note_to_hz('C2')
#     fmax = librosa.note_to_hz('C7')

#     f0, _, _ = librosa.pyin(audio, fmin=fmin, fmax=fmax, sr=sr,
#         frame_length=frame, hop_length=hop, center=False)
    
#     return f0

# DEFAULT_N_MELS = 128
# @librosa_stg_meta
# def grammel(audio, sr, frame=WIN_LEN, hop=HOP_LEN, n_mels=DEFAULT_N_MELS):
#     frame = int(frame)
#     hop = int(hop)
#     n_mels = int(n_mels)

#     S = librosa.feature.melspectrogram(y=audio, sr=sr,
#         n_fft=frame, hop_length=hop,n_mels=n_mels, center=False)
    
#     return librosa.power_to_db(S, ref=np.max)
    



if __name__ == '__main__':
    audio = 'audio/YellowRiverInstrument.wav'
    sr = None

    len_frame = 50
    stgs = {
        'beatplp': {
            'hop': HOP_LEN,
            'len_frame': len_frame,
            'tempo_min': 150,
            'tempo_max': 400
        }
    }

    ctx = LibrosaContext(audio=audio, sr=sr, stg=stgs)
    features = ctx.audio_features()

    sr = ctx.sr
    dur = HOP_LEN * len_frame / sr
    print (f'Frame Duration {dur:.2f}s')
    ctx.save_features()