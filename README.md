# Spectograma

A real-time audio visualization application for macOS that captures and visualizes system audio output through dual visualization: a dynamic waveform display and a real-time spectrogram.

## Features

- **Real-time System Audio Capture**: Captures all audio output from your macOS system
- **Dual Visualization**: 
  - Dynamic waveform display that pulsates with audio playback
  - Real-time spectrogram showing frequency content
- **Native macOS Application**: Optimized for Apple Silicon (M1) and macOS Sequoia
- **Lightweight Performance**: Designed for continuous background operation

## Requirements

- macOS Sequoia 15.3.2 or later
- Apple Silicon Mac (M1 or newer)
- Python 3.10+ (ARM64 native via Homebrew)
- BlackHole virtual audio device (for system audio capture)

## Installation

### 1. Install Python dependencies

```bash
# Install dependencies
pip install -r requirements.txt
```

### 2. Set up BlackHole for system audio capture

BlackHole is a modern virtual audio driver that allows applications to capture system audio output.

1. Install BlackHole using Homebrew:
```bash
brew install blackhole-2ch
```

2. Configure macOS to use BlackHole:
   - Open "System Settings" > "Sound"
   - Under "Output", select "BlackHole 2ch"
   - Create a Multi-Output Device (optional for monitoring):
     1. Open "Audio MIDI Setup" (search in Spotlight)
     2. Click the "+" button in the bottom left corner and select "Create Multi-Output Device"
     3. Check both your regular audio output (speakers/headphones) and "BlackHole 2ch"
     4. Make this Multi-Output Device your default output in System Settings > Sound

When properly configured, all system audio will be routed through BlackHole, allowing Spectograma to capture it.

## Usage

1. Run the application:
```bash
python spectograma.py
```

2. In the application:
   - Select "BlackHole 2ch" from the device dropdown
   - Click "Start Capture" to begin visualization
   - The waveform will display at the top and the spectrogram at the bottom
   - The application window is resizable for comfortable viewing on any monitor

3. For best performance:
   - Keep the application running on a secondary monitor if available
   - The application is optimized for low resource usage but displaying high-resolution visualizations

## Troubleshooting

- **No audio devices shown**: Click "Refresh" to rescan audio devices
- **No audio detected**: Ensure BlackHole is properly set as your system output device
- **Performance issues**: Try reducing the window size or moving the application to a secondary display

## Technical Details

- **Audio Capture**: Using sounddevice with PortAudio backend (44.1kHz sample rate)
- **Processing**: NumPy for FFT and frequency analysis
- **Visualization**: PyQtGraph for optimized real-time graphics
- **Interface**: PySide6/PyQt6 for native macOS UI components

## Project Structure

- `src/audio_capture.py`: Handles system audio capture
- `src/audio_processing.py`: Processes audio data and performs FFT
- `src/gui.py`: Manages visualization and user interface
- `src/main.py`: Application entry point and initialization
- `spectograma.py`: Launcher script
# SPECtations
