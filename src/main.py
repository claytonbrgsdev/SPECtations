"""
Main entry point for Spectograma application.
Initializes audio capture, processing, and GUI components.
"""
import sys
import signal
from PySide6 import QtWidgets

from audio_capture import AudioCapture
from audio_processing import AudioProcessor
from gui import SpectogramaGUI


def main():
    """Initialize and run the Spectograma application."""
    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    # Create application
    app = QtWidgets.QApplication(sys.argv)
    
    # Set up audio parameters
    sample_rate = 44100  # Reverted to original value
    chunk_size = 1024    # Reverted to original value
    channels = 2
    
    # Initialize components
    audio_capture = AudioCapture(
        sample_rate=sample_rate,
        chunk_size=chunk_size,
        channels=channels
    )
    
    audio_processor = AudioProcessor(
        sample_rate=sample_rate,
        chunk_size=chunk_size,
        channels=channels
    )
    
    # Create and show GUI
    window = SpectogramaGUI(audio_capture, audio_processor)
    window.show()
    
    # Set application name and icon for better system integration
    app.setApplicationName("Spectograma")
    app.setOrganizationName("Spectograma")
    
    # Set style to fusion for a modern look
    app.setStyle("Fusion")
    
    # Run the application
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
