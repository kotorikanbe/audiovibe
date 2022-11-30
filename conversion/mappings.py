import time, librosa
import numpy as np

from finetune.utils.signal_separation import band_separate, hrps
from finetune.utils.wave_generator import periodic_rectangle_generator
from finetune.utils.signal_analysis import remove_harmonics, extract_peaks
from finetune.utils.ml_basic import extract_clustern
from finetune.utils.global_paras import PEAK_LIMIT
from math import log

def band_select_fast(stft, sr, len_hop, len_window, stft_freq, duty=0.5, vib_extremefreq = [50,500], vib_bias=80, vib_maxbin=255, 
                peak_limit=-1, vib_frame_len=24, **kwargs) -> np.ndarray:
    """
    select frequency band at each time point for mapping to vibration, where vibration frequency is determined by 
    scaling the corresponding audio frequency
    :return: 2d vibration sequence (frame_num, vib_frame_len)
    """
    start_t = time.time()
    linspec = np.abs(stft)**2.0    # power linear spectrogram
    
    # select bins lower than 8k hz
    num_8k_bins = np.sum(stft_freq<=8000)
    linspec = linspec[:num_8k_bins,:]
    stft_freq = stft_freq[:num_8k_bins]
    stft_len_window = len_window

    feat_dim, feat_time = linspec.shape
    global_scale = kwargs.get("global_scale", 0.01)
    hprs_harmonic_filt_len = kwargs.get("hprs_harmonic_filt_len", 0.1)
    hprs_percusive_filt_len = kwargs.get("hprs_percusive_filt_len", 400 * stft_len_window / 512)    # TODO this is determined by experience
    hprs_beta = kwargs.get("hprs_beta", 4.0)
    peak_globalth = kwargs.get("peak_globalth", 20)
    peak_relativeth = kwargs.get("peak_relativeth", 4)
    stft_peak_movlen = int(kwargs.get("stft_peak_movlen", 400//np.abs(stft_freq[2]-stft_freq[1])))    # TODO this is determined by experience
    assert global_scale>0 and global_scale<=1.0, "global scale must be in (0,1]"


    # get relationship between vib-freq and audio-freq
    # we assume they have linear relationship: aud_freq = a * vib_freq + b
    # TODO we need more sophisticated way to model the relationship
    a = float((min(stft_freq)-max(stft_freq))) / (min(vib_extremefreq)-max(vib_extremefreq))
    b = max(stft_freq) - a * max(vib_extremefreq)


    # harmonic-percusive-residual separation
    power_spec_h, power_spec_p, power_spec_r, M_h, M_p, M_r = hrps(linspec, sr, len_harmonic_filt=hprs_harmonic_filt_len,
                                                                   len_percusive_filt=hprs_percusive_filt_len, beta=hprs_beta,
                                                                   len_window=stft_len_window, len_hop=len_hop)
    harm_peaks = extract_peaks(power_spec_h, peak_movlen=stft_peak_movlen, peak_relativeth=peak_relativeth, peak_globalth=peak_globalth)
    spec_mask = harm_peaks

    # get top peaks
    spec_masked = linspec * harm_peaks
    # remove_t = 0    # harmonic removal timer
    if peak_limit<=0:
        # automatically determin peak limit
        # TODO more sophisticated way to determin peak limits
        peak_mask = np.zeros_like(spec_mask)
        power_spec_sum = np.sum(linspec, axis=0)
        power_spec_h_sum = np.sum(power_spec_h, axis=0)
        power_spec_p_sum = np.sum(power_spec_p, axis=0)
        power_spec_r_sum = np.sum(power_spec_r, axis=0)
        h_ratio = power_spec_h_sum / power_spec_sum
        p_ratio = power_spec_p_sum / power_spec_sum
        r_ratio = power_spec_r_sum / power_spec_sum
        for ti in range(feat_time):
            if p_ratio[ti]>=2*r_ratio[ti] and p_ratio[ti]>2*h_ratio[ti]:
                curr_peak_limit = 3
            elif r_ratio[ti]>2*h_ratio[ti]  and r_ratio[ti]>2*p_ratio[ti]:
                curr_peak_limit = 2
            elif h_ratio[ti]>2*p_ratio[ti] and h_ratio[ti]>2*r_ratio[ti]:
                curr_spec_mask = np.expand_dims(harm_peaks[:, ti], axis=1)
                curr_spec = np.expand_dims(linspec[:, ti], axis=1)
                spec_mask_no_harms, curr_spec_mask = remove_harmonics(curr_spec_mask, curr_spec, stft_freq)
                curr_peak_limit = int(min(PEAK_LIMIT, np.sum(spec_mask_no_harms)+1))
            else:
                curr_peak_limit = PEAK_LIMIT
            peak_inds = spec_masked[:,ti].argsort()[::-1][:curr_peak_limit]
            peak_mask[peak_inds, ti] = 1
    else:
        # given pre-set peak_limit
        spec_masked = librosa.power_to_db(spec_masked)
        peak_inds = np.argpartition(spec_masked, -peak_limit, axis=0)[-peak_limit:, :]    # top peaks inds at each time point
        peak_mask = np.zeros_like(spec_mask)
        np.put_along_axis(peak_mask, peak_inds, 1, axis=0)    # set 1 to peak mask where top peaks are seleted
    # incorporate peak's mask
    spec_masked = spec_masked * peak_mask
    

    # generate vibration
    final_vibration = 0
    for f in range(feat_dim):    # per mel bin
        # get vib freq: vib_freq = (aud_freq - b) / a
        curr_aud_freq = stft_freq[f]
        curr_vib_freq = round((curr_aud_freq-b)/a)    # we round it for wave generation
        curr_vib_wav = periodic_rectangle_generator([1,0.], duty=duty, freq=curr_vib_freq, frame_num=feat_time,
                                                  frame_time=len_hop/float(sr), frame_len=vib_frame_len)
        # get vib magnitude
        curr_melspec = spec_masked[f, :]
        curr_vib_mag = np.expand_dims(curr_melspec, axis=1)
        curr_vib_mag = np.tile(curr_vib_mag, (1, vib_frame_len))    # tile to form a matrix (frame_num, frame_len)
        # generate curr vib
        curr_vib = curr_vib_wav * curr_vib_mag
        # accumulate
        if f == 0:
            final_vibration = curr_vib
        else:
            final_vibration += curr_vib

    assert not isinstance(final_vibration,int), "final_vibration is not assigned!"
    
    # post-process
    final_vibration = final_vibration / feat_dim    # average accumulated signal
    final_max = np.max(final_vibration)
    final_min = np.min(final_vibration)
    bin_num = vib_maxbin-vib_bias
    bins = np.linspace(0., 1., bin_num, endpoint=True)    # linear bins for digitizing
    mu_bins = [x*(log(1+bin_num*x)/log(1+bin_num)) for x in bins]    # mu-law bins
    # final normalization
    final_vibration_norm = (final_vibration - final_min) / (final_max - final_min)
    # digitize
    final_vibration_bins = np.digitize(final_vibration_norm, mu_bins)
    final_vibration_bins = final_vibration_bins.astype(np.uint8)
    # add offset
    final_vibration_bins += vib_bias
    # set zeros (we have to do this for body feeling)
    global_min = np.min(spec_masked[np.nonzero(spec_masked)])    # find global minimum except 0
    threshold_val = (PEAK_LIMIT//2) * global_min    # we set zeroing condition: if less than half of {peak_limit} bins have {global_min} values
    threshold_val_norm = (threshold_val - final_min) / (final_max - final_min)
    threshold_val_bin = np.digitize(threshold_val_norm, mu_bins)
    final_vibration_bins[final_vibration_bins<=vib_bias+threshold_val_bin] = 0    # set zeros below threshold
    
    print("mapping elapses: %f" % (time.time()-start_t))
    
    return final_vibration_bins


if __name__ == "__main__":
    stft = np.load("stft.npy")
    len_hop = 128
    len_window = 128
    sr = 22050
    stft_freq = librosa.fft_frequencies(sr=sr, n_fft=len_window)
    kwargs = {}
    # vibration
    kwargs["duty"] = 0.5    # vibration signal duty ratio, if larger than 1, it represents the number of "1"
    kwargs["vib_extremefreq"] = [30,200]    # extreme value of the vibration frequency (highest and lowest frequency)
    kwargs["vib_bias"] = 80    # zero-feeling offset
    kwargs["vib_maxbin"] = 255    # number of bins for digitizing vibration magnitude
    kwargs["peak_limit"] = -1    # the limit of peaks selected for vibration generation (at most this many components will be included in final vibration at current time)
    kwargs["vib_frame_len"] = 12    # vibration signal sample number for each output frame
    kwargs["global_scale"] = 1.0    # the global scale for vibration tense
    kwargs["streaming"] = False    # flag to use streaming inference
    kwargs["audio_len"] = 0.1    # seconds of the audio window in streaming inference
    kwargs["stream_nwin"] = 1    # number of streaming inferencing windows in mapping buffer. Mapping algo will be performed over it and the center window's result will be output.
    # signal analysis
    kwargs["peak_globalth"] = 20    # global threshold for peak detection in dB (difference from the max value at current time)
    kwargs["peak_relativeth"] = 4    # local threshold for peak detection in dB (difference over the moving average at current time)
    kwargs["mel_peak_movlen"] = 5    # moving average length (in number of bins) along frequency axis
    kwargs["stft_peak_movlen"] = 19    # moving average length (in number of bins) along frequency axis
    kwargs["hprs_harmonic_filt_len"] = 0.1    # HPRS harmonic direction filter length (in sec)
    kwargs["hprs_percusive_filt_len"] = 400    # HPRS percusive direction filter length (in hz)
    kwargs["hprs_beta"] = 4.0    # HPRS harmonic and percusive threshold factor
    band_select_fast(stft, sr, len_hop, len_window, stft_freq, duty=0.5, vib_extremefreq = kwargs["vib_extremefreq"], vib_bias=80, vib_maxbin=255, 
                peak_limit=-1, vib_frame_len=24, **kwargs)