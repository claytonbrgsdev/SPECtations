"""
Audio processing module for Spectograma.
Handles audio analysis including FFT for spectrogram generation.
"""
import numpy as np
from scipy import signal


class AudioProcessor:
    def __init__(self, sample_rate=44100, chunk_size=1024, channels=1):
        """
        Initialize audio processor with given parameters.
        
        Args:
            sample_rate (int): Sampling rate in Hz
            chunk_size (int): Chunk size in samples
            channels (int): Number of audio channels
        """
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.channels = channels
        
        # Default window function
        self.window = np.hanning(chunk_size)
        
        # Default waveform settings
        self.waveform_settings = {
            'amplitude_scale': 1.0,
            'normalization': 'Dynamic',
            'sensitivity': 1.0,
            'time_range_percent': 100
        }
        
        # Frequency bins for the FFT
        self.freqs = np.fft.rfftfreq(chunk_size, 1/sample_rate)
        
        # Overlap for STFT to improve temporal resolution
        self.hop_length = chunk_size // 2
        
    def process_audio(self, audio_data):
        """
        Process raw audio data to extract waveform and frequency information.
        
        Args:
            audio_data (numpy.ndarray): Raw audio data from capture
            
        Returns:
            tuple: (waveform, spectrum) where:
                  - waveform is the processed audio waveform
                  - spectrum is the frequency spectrum from FFT
        """
        if audio_data is None:
            return None, None
        
        # If stereo, convert to mono by averaging channels
        if self.channels > 1:
            waveform = np.mean(audio_data, axis=1)
        else:
            waveform = audio_data.flatten()
        
        # Get normalization settings
        normalization = self.waveform_settings.get('normalization', 'Dynamic')
        sensitivity = self.waveform_settings.get('sensitivity', 1.0)
        amplitude_scale = self.waveform_settings.get('amplitude_scale', 1.0)
        
        # Apply normalization based on selected method
        max_val = np.max(np.abs(waveform))
        if max_val > 0.01:  # Only normalize if there's a meaningful signal
            if normalization == 'Dynamic':
                # Dynamic normalization - more sensitive to quiet sounds
                # Higher sensitivity means stronger normalization for quiet sounds
                norm_factor = sensitivity / (max_val + (0.2 / sensitivity))
                # Limit to avoid excessive amplification
                norm_factor = min(norm_factor, sensitivity * 5.0)
                waveform = waveform * norm_factor
            elif normalization == 'Fixed':
                # Fixed normalization - constant ratio
                waveform = waveform * (0.5 / max_val)
            # If 'None', no normalization is applied
        
        # Apply user-defined amplitude scaling
        waveform = waveform * amplitude_scale
        
        # Apply window function to reduce spectral leakage
        windowed = waveform * self.window
        
        # Compute FFT
        spectrum = np.abs(np.fft.rfft(windowed))
        
        # Convert to dB scale with moderate threshold
        min_val = 1e-10
        spectrum = 20 * np.log10(np.maximum(min_val, spectrum))
        
        return waveform, spectrum
    
    def compute_spectrogram(self, audio_buffer, n_fft=2048, hop_length=None):
        """
        Compute a spectrogram from a buffer of audio data.
        
        Args:
            audio_buffer (numpy.ndarray): Buffer of audio data
            n_fft (int): FFT window size
            hop_length (int): Number of samples between frames
            
        Returns:
            tuple: (frequencies, times, spectrogram)
        """
        if audio_buffer is None or len(audio_buffer) == 0:
            return None, None, None
        
        if hop_length is None:
            hop_length = n_fft // 4  # 75% overlap for better time resolution
        
        # If stereo, convert to mono by averaging channels
        if audio_buffer.ndim > 1 and audio_buffer.shape[1] > 1:
            audio_data = np.mean(audio_buffer, axis=1)
        else:
            audio_data = audio_buffer.flatten()
        
        # Use a safer normalization for the spectrogram
        max_val = np.max(np.abs(audio_data))
        if max_val > 0.01:  # Only normalize if there's a meaningful signal
            audio_data = audio_data * (0.5 / max_val)
        
        # Compute spectrogram using STFT
        f, t, Sxx = signal.spectrogram(
            audio_data,
            fs=self.sample_rate,
            window='hann',  # Back to reliable hann window
            nperseg=n_fft,
            noverlap=n_fft - hop_length,
            detrend=False,
            scaling='spectrum'
        )
        
        # Convert to dB scale with standard threshold
        min_val = 1e-10
        Sxx_db = 10 * np.log10(np.maximum(min_val, Sxx))
        
        return f, t, Sxx_db
    
    def get_freq_bins(self):
        """
        Get the frequency bins for FFT analysis.
        
        Returns:
            numpy.ndarray: Array of frequency values corresponding to FFT bins
        """
        return self.freqs

    def get_latest_data(self):
        """Get the latest processed waveform and spectrum data.
        
        Returns:
            tuple: (waveform, spectrum) - the latest processed audio data
        """
        # Get the latest audio data from the capture component
        audio_data = self.audio_capture.get_audio_chunk()
        
        if audio_data is not None:
            # Process audio data
            waveform, spectrum = self.process_audio(audio_data)
            return waveform, spectrum
        
        # Return empty data if no audio is available
        return np.zeros(self.chunk_size), np.zeros(self.chunk_size // 2 + 1)
