"""
Audio capture module for Spectograma.
Responsible for capturing system audio output using sounddevice and PortAudio.
"""
import queue
import sounddevice as sd
import numpy as np

class AudioCapture:
    def __init__(self, sample_rate=44100, chunk_size=1024, channels=2):
        """
        Initialize audio capture with specified parameters.
        
        Args:
            sample_rate (int): Audio sample rate in Hz (default: 44100)
            chunk_size (int): Number of frames per chunk (default: 1024)
            channels (int): Number of audio channels (default: 2 for stereo)
        """
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.channels = channels
        self.audio_queue = queue.Queue(maxsize=10)  # Reverted to original size
        self.stream = None
        self.is_running = False
        
        # Get list of available devices for user reference
        self.devices = sd.query_devices()
    
    def get_device_list(self):
        """Return a list of available audio devices."""
        return self.devices
    
    def start_capture(self, device_id=None):
        """
        Start capturing audio from the specified device.
        
        Args:
            device_id: ID of the device to capture from (default: None, uses system default)
                       For BlackHole, find the device ID from get_device_list()
        """
        if self.is_running:
            return
        
        def audio_callback(indata, frames, time, status):
            """Callback for sounddevice stream to process incoming audio."""
            if status:
                print(f"Audio callback status: {status}")
            
            # Debug: Check if we're receiving audio data
            signal_level = np.max(np.abs(indata)) if indata is not None else 0
            if signal_level > 0.01:  # Only print when there's a significant signal
                print(f"Audio signal detected! Level: {signal_level:.6f}")
            elif frames % 100 == 0:  # Print periodically to confirm callback is running
                print(f"Audio callback running, but signal level is low: {signal_level:.6f}")
                
            # Put audio data in the queue
            try:
                self.audio_queue.put(indata.copy(), block=False)
            except queue.Full:
                # Queue is full, discard old data
                try:
                    self.audio_queue.get_nowait()
                    self.audio_queue.put(indata.copy(), block=False)
                except queue.Empty:
                    pass
        
        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                blocksize=self.chunk_size,
                device=device_id,
                channels=self.channels,
                callback=audio_callback
            )
            self.stream.start()
            self.is_running = True
            print(f"Audio capture started with sample rate: {self.sample_rate}Hz, "
                  f"chunk size: {self.chunk_size}, device: {device_id or 'default'}")
        except Exception as e:
            print(f"Error starting audio capture: {e}")
            raise
    
    def stop_capture(self):
        """Stop audio capture."""
        if self.stream and self.is_running:
            self.stream.stop()
            self.stream.close()
            self.stream = None
            self.is_running = False
            print("Audio capture stopped")
    
    def get_audio_chunk(self, timeout=0.1):
        """
        Get the latest audio chunk from the queue.
        
        Args:
            timeout (float): Time to wait for audio data in seconds
            
        Returns:
            numpy.ndarray: Audio data, or None if no data is available
        """
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None
