"""
GUI module for Spectograma.
Handles the main application window and real-time visualizations.
"""
import numpy as np
import pyqtgraph as pg
import json
import os
import datetime
import time
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtCore import Qt, QTimer, QBuffer
from PySide6.QtGui import QColor, QPalette, QImage, QPainter, QAction
import glob


class SpectogramaGUI(QtWidgets.QMainWindow):
    """Main GUI window for Spectograma."""
    
    def __init__(self, audio_capture, audio_processor):
        """Initialize the GUI."""
        super().__init__()
        
        self.setWindowTitle("Spectograma")
        self.setGeometry(100, 100, 1200, 800)
        
        # Store audio components
        self.audio_capture = audio_capture
        self.audio_processor = audio_processor
        
        # Set default colors
        self.waveform_color = QColor('#3498db')  # Nice blue color
        self.mid_color = QColor('green')
        self.treble_color = QColor('blue')
        
        # State tracking
        self.is_capturing = False
        # Use the presets directory in the project root
        self.presets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "presets")
        
        # Ensure presets directory exists
        os.makedirs(self.presets_dir, exist_ok=True)
        
        # Recording state
        self.is_recording = False
        self.recorded_frames = []
        
        # Output window
        self.output_window = None
        
        # List to store visualization panels
        self.viz_panels = []
        
        # Initialize particles data for visualization
        self.particles_data = {}
        self.current_num_panels = 2  # Default starting with 2 panels
        
        # Dictionary of visualization types mapped to setup functions
        self.viz_types = {
            "Waveform": self.setup_waveform_viz,
            "Spectrogram": self.setup_spectrogram_viz,
            "Spectrum": self.setup_spectrum_viz
        }
        
        # Create spectrogram buffer (rows=time, cols=frequency bins)
        buffer_seconds = 5  # Default buffer size
        # Calculate buffer size based on sample rate and chunk size
        updates_per_second = self.audio_processor.sample_rate / self.audio_processor.chunk_size
        self.buffer_size = int(buffer_seconds * updates_per_second)
        # Try to get frequency bins or create fallback
        try:
            self.fft_freqs = self.audio_processor.get_freq_bins()
            freq_bins = len(self.fft_freqs)
        except AttributeError:
            # Fallback if get_freq_bins() doesn't exist
            freq_bins = self.audio_processor.chunk_size // 2 + 1
            self.fft_freqs = np.linspace(0, self.audio_processor.sample_rate / 2, freq_bins)
            
        self.spectrogram_buffer = np.zeros((self.buffer_size, freq_bins))
        
        # Initialize data for different visualizations
        self.current_waveform = None
        self.current_spectrum = None
        
        # Create empty containers for visualization references
        self.setup_default_visualizations()
        
        # Setup UI
        self.setup_ui()
        
        # Set up timer for visualization updates
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_timer_event)
        # Slow down the update rate for more readable waveform movement
        self.update_timer.start(1000 // 15)  # 15 FPS updates (slower than original 30 FPS)
        
        # Add separate timer for particle animations to ensure smooth updates
        self.particles_timer = QTimer()
        self.particles_timer.timeout.connect(self.update_particles)
        self.particles_timer.start(16)  # ~60fps for smooth animation
        
        # For status tracking
        self.is_capturing = False
        self.is_recording = False
        self.recorded_frames = []
    
    def setup_ui(self):
        """Set up the user interface components."""
        # Main layout
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        
        # Top control bar
        control_bar = QtWidgets.QHBoxLayout()
        
        # Audio device selection
        device_label = QtWidgets.QLabel("Audio Device:")
        self.device_combo = QtWidgets.QComboBox()
        self.refresh_devices()  # Populate device combo box
        
        # Refresh button for audio devices
        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_devices)
        
        # Capture toggle button
        self.capture_btn = QtWidgets.QPushButton("Start Capture")
        self.capture_btn.clicked.connect(self.toggle_capture)
        
        # Settings button for advanced options
        settings_btn = QtWidgets.QPushButton("Settings")
        settings_btn.clicked.connect(self.toggle_settings_panel)
        
        # Presets button
        self.presets_button = QtWidgets.QPushButton("Presets")
        self.presets_button.clicked.connect(self.toggle_presets_panel)
        
        # Add widgets to control bar
        control_bar.addWidget(device_label)
        control_bar.addWidget(self.device_combo)
        control_bar.addWidget(refresh_btn)
        control_bar.addWidget(self.capture_btn)
        control_bar.addWidget(settings_btn)
        control_bar.addWidget(self.presets_button)
        
        # Add control bar to main layout
        main_layout.addLayout(control_bar)
        
        # Second control bar for visualization panels
        viz_control_bar = QtWidgets.QHBoxLayout()
        
        # Panel count selector
        panel_count_label = QtWidgets.QLabel("Visualization Panels:")
        self.panel_count_combo = QtWidgets.QComboBox()
        self.panel_count_combo.addItems(["1", "2", "3", "4"])
        self.panel_count_combo.setCurrentIndex(0)  # Default to 1 panel
        self.panel_count_combo.currentIndexChanged.connect(self.update_panel_count)
        
        # Output window toggle
        output_window_btn = QtWidgets.QPushButton("Open Output Window")
        output_window_btn.clicked.connect(self.toggle_output_window)
        
        # Add sync button for output window
        self.sync_output_btn = QtWidgets.QPushButton("Sync Output")
        self.sync_output_btn.clicked.connect(self.force_sync_output_window)
        self.sync_output_btn.setEnabled(False)  # Disabled until output window is opened
        
        # Add widgets to visualization control bar
        viz_control_bar.addWidget(panel_count_label)
        viz_control_bar.addWidget(self.panel_count_combo)
        viz_control_bar.addWidget(output_window_btn)
        viz_control_bar.addWidget(self.sync_output_btn)
        viz_control_bar.addStretch(1)  # Push widgets to the left
        
        # Add visualization control bar to main layout
        main_layout.addLayout(viz_control_bar)
        
        # Create visualization panel container
        self.viz_panel_container = QtWidgets.QSplitter(Qt.Vertical)
        
        # Initialize visualization panels
        self.initialize_visualization_panels()
        
        # Add visualization container to main layout
        main_layout.addWidget(self.viz_panel_container, 1)  # Give it stretch priority
        
        # Create settings panel (hidden by default)
        self.settings_panel = QtWidgets.QWidget()
        self.settings_panel.setVisible(False)
        settings_layout = QtWidgets.QVBoxLayout(self.settings_panel)
        
        # Settings panel - different tabs for different types of settings
        self.settings_tabs = QtWidgets.QTabWidget()
        
        # Waveform settings tab
        waveform_tab = QtWidgets.QWidget()
        waveform_layout = QtWidgets.QFormLayout(waveform_tab)
        
        # Waveform color
        waveform_color_layout = QtWidgets.QHBoxLayout()
        self.waveform_color_btn = QtWidgets.QPushButton()
        self.set_button_color(self.waveform_color_btn, self.waveform_color)
        self.waveform_color_btn.clicked.connect(self.choose_waveform_color)
        waveform_color_layout.addWidget(self.waveform_color_btn)
        waveform_color_layout.addWidget(QtWidgets.QLabel("Waveform Color"))
        waveform_layout.addRow("", waveform_color_layout)
        
        # Waveform width
        self.waveform_width_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.waveform_width_slider.setMinimum(1)
        self.waveform_width_slider.setMaximum(5)
        self.waveform_width_slider.setValue(2)
        self.waveform_width_slider.valueChanged.connect(self.update_waveform_settings)
        waveform_layout.addRow("Line Width:", self.waveform_width_slider)
        
        # Waveform fill
        self.waveform_fill_check = QtWidgets.QCheckBox("Fill Under Curve")
        self.waveform_fill_check.setChecked(False)
        self.waveform_fill_check.stateChanged.connect(self.update_waveform_settings)
        waveform_layout.addRow("", self.waveform_fill_check)
        
        # Amplitude scale
        self.amplitude_scale_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.amplitude_scale_slider.setMinimum(1)
        self.amplitude_scale_slider.setMaximum(20)
        self.amplitude_scale_slider.setValue(10)
        self.amplitude_scale_slider.valueChanged.connect(self.update_waveform_settings)
        waveform_layout.addRow("Amplitude Scale:", self.amplitude_scale_slider)
        
        # Add a value label for the amplitude scale
        self.amplitude_scale_value = QtWidgets.QLabel("1.0")
        waveform_layout.addRow("", self.amplitude_scale_value)
        self.amplitude_scale_slider.valueChanged.connect(
            lambda v: self.amplitude_scale_value.setText(f"{v/10:.1f}")
        )
        self.amplitude_scale_value.setText(f"{self.amplitude_scale_slider.value()/10:.1f}")
        
        # Normalization method
        self.normalization_combo = QtWidgets.QComboBox()
        self.normalization_combo.addItems(["Dynamic", "Fixed", "None"])
        self.normalization_combo.setCurrentText("Dynamic")
        self.normalization_combo.currentTextChanged.connect(self.update_waveform_settings)
        waveform_layout.addRow("Normalization:", self.normalization_combo)
        
        # Sensitivity for dynamic normalization
        self.sensitivity_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.sensitivity_slider.setMinimum(1)
        self.sensitivity_slider.setMaximum(20)
        self.sensitivity_slider.setValue(10)
        self.sensitivity_slider.valueChanged.connect(self.update_waveform_settings)
        waveform_layout.addRow("Sensitivity:", self.sensitivity_slider)
        
        # Add a value label for the sensitivity
        self.sensitivity_value = QtWidgets.QLabel("1.0")
        waveform_layout.addRow("", self.sensitivity_value)
        self.sensitivity_slider.valueChanged.connect(
            lambda v: self.sensitivity_value.setText(f"{v/10:.1f}")
        )
        self.sensitivity_value.setText(f"{self.sensitivity_slider.value()/10:.1f}")
        
        # Time display range (samples to show)
        self.time_range_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.time_range_slider.setMinimum(10)
        self.time_range_slider.setMaximum(100)
        self.time_range_slider.setValue(100)
        self.time_range_slider.valueChanged.connect(self.update_waveform_settings)
        waveform_layout.addRow("Time Range (%):", self.time_range_slider)
        
        # Display grid lines
        self.grid_lines_check = QtWidgets.QCheckBox("Show Grid Lines")
        self.grid_lines_check.setChecked(False)
        self.grid_lines_check.stateChanged.connect(self.update_waveform_settings)
        waveform_layout.addRow("", self.grid_lines_check)
        
        # Show zero reference line
        self.zero_line_check = QtWidgets.QCheckBox("Show Zero Reference Line")
        self.zero_line_check.setChecked(True)
        self.zero_line_check.stateChanged.connect(self.update_waveform_settings)
        waveform_layout.addRow("", self.zero_line_check)
        
        # Peak hold
        self.peak_hold_check = QtWidgets.QCheckBox("Show Peak Hold")
        self.peak_hold_check.setChecked(False)
        self.peak_hold_check.stateChanged.connect(self.update_waveform_settings)
        waveform_layout.addRow("", self.peak_hold_check)
        
        # Peak hold decay rate
        self.peak_decay_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.peak_decay_slider.setMinimum(1)
        self.peak_decay_slider.setMaximum(20)
        self.peak_decay_slider.setValue(5)
        self.peak_decay_slider.valueChanged.connect(self.update_waveform_settings)
        waveform_layout.addRow("Peak Decay Rate:", self.peak_decay_slider)
        
        # Waveform persistence
        self.persistence_check = QtWidgets.QCheckBox("Enable Persistence")
        self.persistence_check.setChecked(False)
        self.persistence_check.stateChanged.connect(self.update_waveform_settings)
        waveform_layout.addRow("", self.persistence_check)
        
        # Persistence decay rate
        self.persistence_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.persistence_slider.setMinimum(1)
        self.persistence_slider.setMaximum(20)
        self.persistence_slider.setValue(10)
        self.persistence_slider.valueChanged.connect(self.update_waveform_settings)
        waveform_layout.addRow("Persistence Decay:", self.persistence_slider)
        
        # Amplitude-based alpha effect
        self.amplitude_alpha_check = QtWidgets.QCheckBox("Amplitude-based Transparency")
        self.amplitude_alpha_check.setChecked(False)
        self.amplitude_alpha_check.stateChanged.connect(self.update_waveform_settings)
        waveform_layout.addRow("", self.amplitude_alpha_check)
        
        # Amplitude alpha sensitivity
        self.amplitude_alpha_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.amplitude_alpha_slider.setMinimum(1)
        self.amplitude_alpha_slider.setMaximum(10)
        self.amplitude_alpha_slider.setValue(5)
        self.amplitude_alpha_slider.valueChanged.connect(self.update_waveform_settings)
        waveform_layout.addRow("Alpha Sensitivity:", self.amplitude_alpha_slider)
        
        # Frequency-based alpha effect
        self.frequency_alpha_check = QtWidgets.QCheckBox("Frequency-based Transparency")
        self.frequency_alpha_check.setChecked(False)
        self.frequency_alpha_check.stateChanged.connect(self.update_waveform_settings)
        waveform_layout.addRow("", self.frequency_alpha_check)
        
        # Particles visualization effect
        self.particles_check = QtWidgets.QCheckBox("Particles Visualization")
        self.particles_check.setChecked(True)  # Start with particles enabled
        self.particles_check.stateChanged.connect(self.update_waveform_settings)
        waveform_layout.addRow("", self.particles_check)
        
        # Particles density control
        self.particles_density_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.particles_density_slider.setMinimum(10)
        self.particles_density_slider.setMaximum(100)
        self.particles_density_slider.setValue(50)
        self.particles_density_slider.valueChanged.connect(self.update_waveform_settings)
        waveform_layout.addRow("Particles Density:", self.particles_density_slider)
        
        # Particles speed control
        self.particles_speed_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.particles_speed_slider.setMinimum(1)
        self.particles_speed_slider.setMaximum(10)
        self.particles_speed_slider.setValue(5)
        self.particles_speed_slider.valueChanged.connect(self.update_waveform_settings)
        waveform_layout.addRow("Particles Speed:", self.particles_speed_slider)
        
        # Add the waveform tab
        self.settings_tabs.addTab(waveform_tab, "Waveform")
        
        # Spectrogram settings tab
        spectrogram_tab = QtWidgets.QWidget()
        spectrogram_layout = QtWidgets.QFormLayout(spectrogram_tab)
        
        # Colormap selection
        self.colormap_combo = QtWidgets.QComboBox()
        available_colormaps = ['viridis', 'plasma', 'inferno', 'magma', 'cividis', 
                               'Greys', 'Purples', 'Blues', 'Greens', 'Oranges', 'Reds',
                               'YlOrBr', 'YlOrRd', 'OrRd', 'PuRd', 'RdPu', 'BuPu',
                               'GnBu', 'PuBu', 'YlGnBu', 'PuBuGn', 'BuGn', 'YlGn',
                               'binary', 'gist_yarg', 'gist_gray', 'gray', 'bone',
                               'pink', 'spring', 'summer', 'autumn', 'winter', 'cool',
                               'Wistia', 'hot', 'afmhot', 'gist_heat', 'copper']
        self.colormap_combo.addItems(available_colormaps)
        self.colormap_combo.setCurrentText('viridis')
        self.colormap_combo.currentTextChanged.connect(self.update_spectrogram_settings)
        spectrogram_layout.addRow("Colormap:", self.colormap_combo)
        
        # dB range
        min_db_layout = QtWidgets.QHBoxLayout()
        self.min_db_spin = QtWidgets.QSpinBox()
        self.min_db_spin.setRange(-120, 0)
        self.min_db_spin.setValue(-60)
        self.min_db_spin.valueChanged.connect(self.update_spectrogram_settings)
        min_db_layout.addWidget(self.min_db_spin)
        min_db_layout.addWidget(QtWidgets.QLabel("dB"))
        spectrogram_layout.addRow("Min Level:", min_db_layout)
        
        max_db_layout = QtWidgets.QHBoxLayout()
        self.max_db_spin = QtWidgets.QSpinBox()
        self.max_db_spin.setRange(-60, 0)
        self.max_db_spin.setValue(0)
        self.max_db_spin.valueChanged.connect(self.update_spectrogram_settings)
        max_db_layout.addWidget(self.max_db_spin)
        max_db_layout.addWidget(QtWidgets.QLabel("dB"))
        spectrogram_layout.addRow("Max Level:", max_db_layout)
        
        # Frequency range
        min_freq_layout = QtWidgets.QHBoxLayout()
        self.min_freq_spin = QtWidgets.QSpinBox()
        self.min_freq_spin.setRange(0, 5000)
        self.min_freq_spin.setValue(0)
        self.min_freq_spin.valueChanged.connect(self.update_spectrogram_settings)
        min_freq_layout.addWidget(self.min_freq_spin)
        min_freq_layout.addWidget(QtWidgets.QLabel("Hz"))
        spectrogram_layout.addRow("Min Frequency:", min_freq_layout)
        
        max_freq_layout = QtWidgets.QHBoxLayout()
        self.max_freq_spin = QtWidgets.QSpinBox()
        self.max_freq_spin.setRange(1000, 22050)
        self.max_freq_spin.setValue(8000)
        self.max_freq_spin.valueChanged.connect(self.update_spectrogram_settings)
        max_freq_layout.addWidget(self.max_freq_spin)
        max_freq_layout.addWidget(QtWidgets.QLabel("Hz"))
        spectrogram_layout.addRow("Max Frequency:", max_freq_layout)
        
        # Add the spectrogram tab
        self.settings_tabs.addTab(spectrogram_tab, "Spectrogram")
        
        # Spectrum settings tab
        spectrum_tab = QtWidgets.QWidget()
        spectrum_layout = QtWidgets.QFormLayout(spectrum_tab)
        
        # Frequency scale type
        self.freq_scale_combo = QtWidgets.QComboBox()
        self.freq_scale_combo.addItems(["Linear", "Logarithmic"])
        self.freq_scale_combo.setCurrentText("Linear")
        self.freq_scale_combo.currentTextChanged.connect(self.update_spectrum_settings)
        spectrum_layout.addRow("Frequency Scale:", self.freq_scale_combo)
        
        # dB range
        self.spectrum_min_db_spin = QtWidgets.QSpinBox()
        self.spectrum_min_db_spin.setRange(-120, 0)
        self.spectrum_min_db_spin.setValue(-80)
        self.spectrum_min_db_spin.valueChanged.connect(self.update_spectrum_settings)
        spectrum_layout.addRow("Min Level (dB):", self.spectrum_min_db_spin)
        
        # Smoothing
        self.spectrum_smooth_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.spectrum_smooth_slider.setMinimum(0)
        self.spectrum_smooth_slider.setMaximum(10)
        self.spectrum_smooth_slider.setValue(2)
        self.spectrum_smooth_slider.valueChanged.connect(self.update_spectrum_settings)
        spectrum_layout.addRow("Smoothing:", self.spectrum_smooth_slider)
        
        # Peak hold
        self.spectrum_peak_hold_check = QtWidgets.QCheckBox("Show Peak Hold")
        self.spectrum_peak_hold_check.setChecked(False)
        self.spectrum_peak_hold_check.stateChanged.connect(self.update_spectrum_settings)
        spectrum_layout.addRow("", self.spectrum_peak_hold_check)
        
        # Peak hold decay rate
        self.spectrum_peak_decay_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.spectrum_peak_decay_slider.setMinimum(1)
        self.spectrum_peak_decay_slider.setMaximum(20)
        self.spectrum_peak_decay_slider.setValue(5)
        self.spectrum_peak_decay_slider.valueChanged.connect(self.update_spectrum_settings)
        spectrum_layout.addRow("Peak Decay Rate:", self.spectrum_peak_decay_slider)
        
        # Show frequency bands
        self.show_bands_check = QtWidgets.QCheckBox("Show Frequency Bands")
        self.show_bands_check.setChecked(False)
        self.show_bands_check.stateChanged.connect(self.update_spectrum_settings)
        spectrum_layout.addRow("", self.show_bands_check)
        
        # Add the spectrum tab
        self.settings_tabs.addTab(spectrum_tab, "Spectrum")
        
        # Add the settings tabs to the settings panel
        settings_layout.addWidget(self.settings_tabs)
        
        # Add settings panel to main layout
        main_layout.addWidget(self.settings_panel)
        
        # Create presets panel (hidden by default)
        self.presets_panel = QtWidgets.QWidget()
        self.presets_panel.setVisible(False)
        presets_layout = QtWidgets.QVBoxLayout(self.presets_panel)
        
        # Preset controls
        preset_controls = QtWidgets.QHBoxLayout()
        self.preset_name_edit = QtWidgets.QLineEdit()
        self.preset_name_edit.setPlaceholderText("Preset Name")
        self.save_preset_button = QtWidgets.QPushButton("Save")
        self.save_preset_button.clicked.connect(self.save_preset)
        
        preset_controls.addWidget(self.preset_name_edit)
        preset_controls.addWidget(self.save_preset_button)
        
        # Preset list
        self.preset_list = QtWidgets.QListWidget()
        self.preset_list.itemDoubleClicked.connect(self.load_preset)
        
        # Preset buttons
        preset_buttons = QtWidgets.QHBoxLayout()
        self.load_preset_button = QtWidgets.QPushButton("Load")
        self.load_preset_button.clicked.connect(self.load_selected_preset)
        self.delete_preset_button = QtWidgets.QPushButton("Delete")
        self.delete_preset_button.clicked.connect(self.delete_preset)
        
        preset_buttons.addWidget(self.load_preset_button)
        preset_buttons.addWidget(self.delete_preset_button)
        
        # Add widgets to presets layout
        presets_layout.addLayout(preset_controls)
        presets_layout.addWidget(self.preset_list)
        presets_layout.addLayout(preset_buttons)
        
        # Add presets panel to main layout
        main_layout.addWidget(self.presets_panel)
        
        # Central widget
        central_widget = QtWidgets.QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)
        
        # Setup status bar
        self.statusBar().showMessage("Ready")
        
        # Initialize devices list
        self.refresh_devices()
    
    def setup_waveform_viz(self, plot_widget, panel_id):
        """Set up a waveform visualization in the given plot widget."""
        # Clear the layout widget
        plot_widget.clear()
        
        # Create a plot item in the layout
        plot_item = plot_widget.addPlot(title="Waveform")
        plot_item.setLabel('left', 'Amplitude')
        plot_item.setLabel('bottom', 'Sample')
        
        # Set Y-range to be more sensitive to audio levels
        # Use a smaller range for higher precision visualization
        amplitude_scale = 0.5  # Reduced from 1.0 for better resolution
        if hasattr(self, 'amplitude_scale_slider'):
            amplitude_scale = self.amplitude_scale_slider.value() * 0.5  # Scale down for more precision
        
        plot_item.setYRange(-amplitude_scale, amplitude_scale)
        plot_item.enableAutoRange(axis='y', enable=False)  # Disable auto-range for controlled view
        
        # Add curve for waveform
        pen_width = 2
        if hasattr(self, 'waveform_width_slider'):
            pen_width = self.waveform_width_slider.value()
        
        pen = pg.mkPen(self.waveform_color, width=pen_width)
        waveform_curve = plot_item.plot(pen=pen)
        
        # Store the curve reference for faster updates
        plot_item.waveform_curve = waveform_curve
        
        # Store the plot_item in the panel data so we can reference it later
        panel_idx = int(panel_id.split('_')[1])
        if panel_idx < len(self.viz_panels):
            self.viz_panels[panel_idx]['plot_item'] = plot_item
            # Also store in the plots dictionary for backward compatibility
            self.viz_panels[panel_idx]['plots']["Waveform"] = plot_item
        
        # Apply fill if enabled
        if hasattr(self, 'waveform_fill_check') and self.waveform_fill_check.isChecked():
            waveform_curve.setFillLevel(0)
            waveform_curve.setFillBrush(pg.mkBrush(self.waveform_color))
        
    def setup_spectrogram_viz(self, plot_widget, name):
        """Set up a spectrogram visualization."""
        # Clear the layout widget
        plot_widget.clear()
        
        # Create a plot item in the layout
        plot_item = plot_widget.addPlot(title="Spectrogram")
        plot_item.setLabel('left', 'Frequency (Hz)')
        plot_item.setLabel('bottom', 'Time')
        
        # Create image item for the spectrogram
        spectrogram_img = pg.ImageItem()
        plot_item.addItem(spectrogram_img)
        
        # Store the image reference on the plot item for later updates
        plot_item.spectrogram_img = spectrogram_img
        
        # Apply colormap with higher contrast
        colormap_name = "viridis"  # Default to a high-contrast colormap
        if hasattr(self, 'colormap_combo'):
            colormap_name = self.colormap_combo.currentText()
            
        colormap = pg.colormap.get(colormap_name)
        spectrogram_img.setLookupTable(colormap.getLookupTable(alpha=True))
        
        # Set levels (intensity range) with enhanced dynamic range
        min_db = -90  # Default for more sensitivity
        max_db = -20  # Default for more sensitivity
        
        if hasattr(self, 'min_db_spin'):
            min_db = self.min_db_spin.value()
        if hasattr(self, 'max_db_spin'):
            max_db = self.max_db_spin.value()
            
        # Enhance the contrast by narrowing the dB range
        spectrogram_img.setLevels([min_db, max_db])
        
        # Set frequency range
        min_freq = 20  # Default to audible range
        max_freq = 20000  # Default to audible range
        
        if hasattr(self, 'min_freq_spin'):
            min_freq = self.min_freq_spin.value()
        if hasattr(self, 'max_freq_spin'):  # Fixed typo: was checking min_freq_spin twice
            max_freq = self.max_freq_spin.value()
            
        plot_item.setYRange(min_freq, max_freq)
        plot_item.enableAutoRange(axis='y', enable=False)  # Disable auto-range for consistent view
        
        # Store the plot_item for later reference
        if isinstance(name, str) and name.startswith('panel_'):
            panel_idx = int(name.split('_')[1])
            if panel_idx < len(self.viz_panels):
                self.viz_panels[panel_idx]['plot_item'] = plot_item
        
    def setup_spectrum_viz(self, plot_widget, panel_id):
        """Set up a spectrum (frequency) visualization in the given plot widget."""
        # Clear the layout widget
        plot_widget.clear()
        
        # Create a plot item in the layout
        plot_item = plot_widget.addPlot(title="Spectrum")
        plot_item.setLabel('left', 'Magnitude (dB)')
        plot_item.setLabel('bottom', 'Frequency (Hz)')
        
        # Use logarithmic X-axis for better frequency visualization
        plot_item.setLogMode(x=True, y=False)
        
        # Set X-range to audio spectrum (20Hz to 20kHz)
        plot_item.setXRange(np.log10(20), np.log10(20000))  # 20Hz to 20kHz
        
        # Set Y-range to enhanced dB range for better precision
        # Use a narrower range to show more detail
        plot_item.setYRange(-100, 0)  # Expanded from -80 to -100 for better low-level detail
        plot_item.enableAutoRange(axis='y', enable=False)  # Disable auto-range for consistent view
        
        # Add curve for spectrum with brighter color for visibility
        pen = pg.mkPen('y', width=2)
        curve = plot_item.plot(pen=pen)
        
        # Store direct reference for faster updates
        plot_item.spectrum_curve = curve
        
        # Store the plot_item for later reference
        panel_idx = int(panel_id.split('_')[1])
        if panel_idx < len(self.viz_panels):
            self.viz_panels[panel_idx]['plot_item'] = plot_item
    
    def update_top_visualization(self):
        """Switch the top visualization based on the selected type."""
        viz_type = self.top_viz_combo.currentText()
        self.top_viz_stack.setCurrentWidget(self.top_plots[viz_type])
    
    def update_bottom_visualization(self):
        """Switch the bottom visualization based on the selected type."""
        viz_type = self.bottom_viz_combo.currentText()
        self.bottom_viz_stack.setCurrentWidget(self.bottom_plots[viz_type])
    
    def refresh_devices(self):
        """Refresh the list of available audio devices."""
        self.device_combo.clear()
        devices = self.audio_capture.get_device_list()
        
        for i, device in enumerate(devices):
            name = f"{i}: {device['name']} ({'in' if device['max_input_channels'] > 0 else ''}{'out' if device['max_output_channels'] > 0 else ''})"
            self.device_combo.addItem(name, i)
            
            # Look for BlackHole or other virtual devices - suggest them for system audio capture
            if "BlackHole" in device['name'] and device['max_input_channels'] > 0:
                self.device_combo.setCurrentIndex(self.device_combo.count() - 1)
        
        self.statusBar().showMessage("Devices refreshed", 3000)
    
    def refresh_presets(self):
        """Refresh the list of available presets."""
        self.preset_combo.clear()
        
        # Add default option
        self.preset_combo.addItem("Default", "default")
        
        # Look for preset files
        if os.path.exists(self.presets_dir):
            preset_files = [f for f in os.listdir(self.presets_dir) if f.endswith('.json')]
            
            for preset_file in preset_files:
                preset_name = os.path.splitext(preset_file)[0]
                self.preset_combo.addItem(preset_name, preset_file)
    
    def toggle_capture(self):
        """Toggle audio capture on/off."""
        if not self.is_capturing:
            device_id = self.device_combo.currentData()
            try:
                self.audio_capture.start_capture(device_id)
                self.capture_btn.setText("Stop Capture")
                self.statusBar().showMessage(f"Capturing from device: {self.device_combo.currentText()}")
                self.is_capturing = True
            except Exception as e:
                self.statusBar().showMessage(f"Error: {str(e)}")
        else:
            self.audio_capture.stop_capture()
            self.capture_btn.setText("Start Capture")
            self.statusBar().showMessage("Capture stopped")
            self.is_capturing = False
    
    def update_particles(self):
        """Update particle animations independent of audio data for smoother animation."""
        if not self.is_capturing:
            return
            
        # Only process if we have active particles
        if not hasattr(self, 'particles_check') or not self.particles_check.isChecked():
            return
            
        # Display a message on first call to confirm this method is being called
        if not hasattr(self, '_particles_message_shown'):
            print("Particles animation timer is running")
            self._particles_message_shown = True
            
        current_time = time.time()
        particle_speed = self.particles_speed_slider.value() / 5.0 if hasattr(self, 'particles_speed_slider') else 1.0
        
        # Update each panel with particles
        for panel in self.viz_panels:
            panel_id = str(id(panel))
            if panel_id in self.particles_data and self.particles_data[panel_id]['particles']:
                # Get particles data
                particles = self.particles_data[panel_id]['particles']
                dt = current_time - self.particles_data[panel_id]['last_update']
                self.particles_data[panel_id]['last_update'] = current_time
                
                # Skip if dt is too large (application was paused)
                if dt > 0.1:
                    dt = 0.016  # Default to 16ms
                
                # Update particle positions
                particles_to_remove = []
                for i, particle in enumerate(particles):
                    # Update position
                    particle['x'] += particle['vx'] * 50 * dt * particle_speed
                    particle['y'] += particle['vy'] * 50 * dt * particle_speed
                    
                    # Add some turbulence
                    particle['vx'] += (np.random.random() - 0.5) * 0.2 * particle_speed
                    particle['vy'] += (np.random.random() - 0.5) * 0.2 * particle_speed
                    
                    # Limit velocity
                    max_vel = 5 * particle_speed
                    particle['vx'] = max(-max_vel, min(max_vel, particle['vx']))
                    particle['vy'] = max(-max_vel, min(max_vel, particle['vy']))
                    
                    # Decrease life
                    particle['life'] -= 0.005 * particle_speed
                    
                    # Remove dead particles
                    if particle['life'] <= 0:
                        particles_to_remove.append(i)
                    # Also remove if out of bounds
                    elif abs(particle['y']) > 1.0:
                        particles_to_remove.append(i)
                
                # Remove dead particles
                for i in sorted(particles_to_remove, reverse=True):
                    if i < len(particles):  # Safety check
                        del particles[i]
                
                # Get waveform plot
                if 'Waveform' in panel['plots']:
                    waveform_plot = panel['plots']['Waveform']
                    
                    # Create new scatter plot
                    if 'particle_main' in panel['plots']:
                        # Remove old scatter plot
                        waveform_plot.getPlotItem().removeItem(panel['plots']['particle_main'])
                        
                        if particles:  # Only recreate if we have particles
                            # Extract particle data
                            x_pos = [p['x'] for p in particles]
                            y_pos = [p['y'] for p in particles]
                            sizes = [p['size'] * p['life'] * 10 for p in particles]
                            colors = [p['color'] for p in particles]
                            
                            # Create new scatter plot with updated positions
                            scatter = pg.ScatterPlotItem()
                            
                            # Create points with large sizes and bright colors
                            points = []
                            for x, y, s, color in zip(x_pos, y_pos, sizes, colors):
                                # Make particles much bigger
                                size = s * 8
                                
                                # Create a bright color
                                bright_color = pg.mkColor('w')
                                bright_color.setHsvF(color.hsvHueF(), 1.0, 1.0, 0.8)
                                
                                # Add point
                                points.append({
                                    'pos': (x, y),
                                    'size': size,
                                    'brush': bright_color,
                                    'pen': pg.mkPen(width=2, color=bright_color)
                                })
                            
                            scatter.setData(points)
                            
                            # Add to plot
                            waveform_plot.getPlotItem().addItem(scatter)
                            panel['plots']['particle_main'] = scatter
    
    def update_timer_event(self):
        """Update timer event handler - called at regular intervals to update visualizations."""
        if not self.is_capturing:
            return
        
        # Debug counter to print periodic status messages
        if not hasattr(self, '_debug_counter'):
            self._debug_counter = 0
        self._debug_counter += 1
            
        # Get the latest audio data
        audio_data = self.audio_capture.get_audio_chunk()
        
        # Debug: Print status info every 50 frames
        if self._debug_counter % 50 == 0:
            if audio_data is not None:
                signal_level = np.max(np.abs(audio_data))
                print(f"[GUI] Audio data received, max signal level: {signal_level:.6f}")
            else:
                print("[GUI] No audio data received from capture device")
            device_name = self.device_combo.currentText() if hasattr(self, 'device_combo') else "Unknown"
            device_id = self.device_combo.currentData() if hasattr(self, 'device_combo') else "None"
            print(f"[GUI] Current audio device: {device_name}, ID: {device_id}")
        
        if audio_data is None:
            return
            
        # Process audio data
        waveform_data, spectrum_data = self.audio_processor.process_audio(audio_data)
        if waveform_data is None or spectrum_data is None:
            return
            
        # Update spectrogram buffer
        if spectrum_data is not None:
            self.spectrogram_buffer = np.roll(self.spectrogram_buffer, -1, axis=0)
            self.spectrogram_buffer[-1] = spectrum_data
            
        # Update the visualizations in all panels
        for panel_idx, panel in enumerate(self.viz_panels):
            # Get the current visualization type for this panel
            viz_type = panel['combo'].currentText()
            
            # Update the appropriate visualization
            if viz_type == "Waveform" and waveform_data is not None:
                if "Waveform" in panel['plots']:
                    waveform_plot = panel['plots']["Waveform"]
                    if hasattr(waveform_plot, 'waveform_curve'):
                        waveform_curve = waveform_plot.waveform_curve
                        
                        # Check for particles visualization effect
                        if hasattr(self, 'particles_check') and self.particles_check.isChecked():
                            print("Particles visualization enabled")
                            # Remove previous particle plots
                            for key in list(panel['plots'].keys()):
                                if key.startswith('particle_'):
                                    waveform_plot.getPlotItem().removeItem(panel['plots'][key])
                                    del panel['plots'][key]
                            
                            # Hide main waveform curve
                            waveform_curve.hide()
                            
                            # Initialize panel's particles if needed
                            panel_id = str(id(panel))
                            if panel_id not in self.particles_data:
                                self.particles_data[panel_id] = {
                                    'particles': [],
                                    'last_update': time.time()
                                }
                            
                            # Get particle settings
                            num_particles = self.particles_density_slider.value()
                            particle_speed = self.particles_speed_slider.value() / 5.0  # Range 0.2-2.0
                            
                            # Get current time for animation
                            current_time = time.time()
                            dt = current_time - self.particles_data[panel_id]['last_update']
                            self.particles_data[panel_id]['last_update'] = current_time
                            
                            # Generate or update particles
                            if not self.particles_data[panel_id]['particles'] or len(self.particles_data[panel_id]['particles']) != num_particles:
                                # Create new particles
                                self.particles_data[panel_id]['particles'] = []
                                for i in range(num_particles):
                                    # Random position along the waveform
                                    x_pos = np.random.randint(0, len(waveform_data))
                                    # Y position based on waveform value at that point
                                    y_pos = waveform_data[x_pos] if x_pos < len(waveform_data) else 0
                                    # Random velocity
                                    vx = (np.random.random() - 0.5) * particle_speed
                                    vy = (np.random.random() - 0.5) * particle_speed
                                    # Random size
                                    size = np.random.randint(2, 8)
                                    # Color based on position (phase shift across spectrum)
                                    color_val = (i / num_particles) * 360
                                    color = pg.mkColor(color_val, 1.0, 0.8, mode='hsv')
                                    
                                    self.particles_data[panel_id]['particles'].append({
                                        'x': x_pos,
                                        'y': y_pos,
                                        'vx': vx,
                                        'vy': vy,
                                        'size': size,
                                        'color': color,
                                        'life': 1.0  # Full life
                                    })
                            else:
                                # Update existing particles
                                particles_to_remove = []
                                for i, particle in enumerate(self.particles_data[panel_id]['particles']):
                                    # Get audio amplitude at this position to influence particle
                                    x_idx = int(particle['x']) % len(waveform_data)
                                    audio_influence = abs(waveform_data[x_idx]) * 5.0
                                    
                                    # Update position with velocity and audio influence
                                    particle['x'] += particle['vx'] * (1 + audio_influence) * 10 * dt * particle_speed
                                    particle['y'] += particle['vy'] * (1 + audio_influence) * 10 * dt * particle_speed
                                    
                                    # Add some turbulence based on audio data
                                    particle['vx'] += (np.random.random() - 0.5) * audio_influence * 0.5
                                    particle['vy'] += (np.random.random() - 0.5) * audio_influence * 0.5
                                    
                                    # Limit velocity
                                    max_vel = 5 * particle_speed
                                    particle['vx'] = max(-max_vel, min(max_vel, particle['vx']))
                                    particle['vy'] = max(-max_vel, min(max_vel, particle['vy']))
                                    
                                    # Decrease life
                                    particle['life'] -= 0.01 * particle_speed
                                    
                                    # Remove dead particles
                                    if particle['life'] <= 0:
                                        particles_to_remove.append(i)
                                    elif particle['x'] < 0 or particle['x'] >= len(waveform_data) or abs(particle['y']) > 1.0:
                                        particles_to_remove.append(i)
                                
                                # Remove dead particles (in reverse order to avoid index issues)
                                for i in sorted(particles_to_remove, reverse=True):
                                    del self.particles_data[panel_id]['particles'][i]
                                
                                # Add new particles to replace removed ones
                                for i in range(len(particles_to_remove)):
                                    x_pos = np.random.randint(0, len(waveform_data))
                                    y_pos = waveform_data[x_pos] if x_pos < len(waveform_data) else 0
                                    vx = (np.random.random() - 0.5) * particle_speed
                                    vy = (np.random.random() - 0.5) * particle_speed
                                    size = np.random.randint(2, 8)
                                    color_val = (np.random.random()) * 360
                                    color = pg.mkColor(color_val, 1.0, 0.8, mode='hsv')
                                    
                                    self.particles_data[panel_id]['particles'].append({
                                        'x': x_pos,
                                        'y': y_pos,
                                        'vx': vx,
                                        'vy': vy,
                                        'size': size,
                                        'color': color,
                                        'life': 1.0
                                    })
                            
                            # Create scatter plot for particles
                            particles = self.particles_data[panel_id]['particles']
                            print(f"Number of particles: {len(particles)}")
                            if particles:
                                x_pos = [p['x'] for p in particles]
                                y_pos = [p['y'] for p in particles]
                                sizes = [p['size'] * p['life'] * 10 for p in particles]  # Size decreases with life
                                colors = [p['color'] for p in particles]
                                
                                # Create scatter plot item - use much larger particles with bright colors
                                scatter = pg.ScatterPlotItem()
                                
                                # Create points with much larger sizes and brighter colors
                                points = []
                                for x, y, s, color in zip(x_pos, y_pos, sizes, colors):
                                    # Make particles much bigger
                                    size = s * 8  # Larger size multiplier
                                    
                                    # Create a bright brush with full opacity
                                    bright_color = pg.mkColor('w')  # Start with white
                                    bright_color.setHsvF(color.hsvHueF(), 1.0, 1.0, 0.8)  # Full saturation and value
                                    
                                    # Add point with outline
                                    points.append({
                                        'pos': (x, y),
                                        'size': size,
                                        'brush': bright_color,
                                        'pen': pg.mkPen(width=2, color=bright_color)  # Thicker outline
                                    })
                                
                                scatter.setData(points)
                                print(f"Created scatter plot with {len(points)} points")
                                
                                # Add to plot
                                waveform_plot.getPlotItem().addItem(scatter)
                                panel['plots']['particle_main'] = scatter
                        
                        # Check for amplitude-based alpha effect
                        elif hasattr(self, 'amplitude_alpha_check') and self.amplitude_alpha_check.isChecked():
                            # Remove previous segment curves
                            for key in list(panel['plots'].keys()):
                                if key.startswith('segment_'):
                                    waveform_plot.getPlotItem().removeItem(panel['plots'][key])
                                    del panel['plots'][key]
                            
                            # Hide main waveform curve
                            waveform_curve.hide()
                            
                            # Create segments with alpha based on amplitude
                            max_amplitude = np.max(np.abs(waveform_data))
                            if max_amplitude > 0:  # Avoid division by zero
                                # Get sensitivity from slider
                                sensitivity = self.amplitude_alpha_slider.value() / 5.0  # Range 0.2-2.0
                                
                                # Segment the waveform for varying alpha
                                segment_size = 50  # Number of samples per segment
                                segments = len(waveform_data) // segment_size
                                
                                for i in range(segments):
                                    start_idx = i * segment_size
                                    end_idx = min((i + 1) * segment_size, len(waveform_data))
                                    segment_data = waveform_data[start_idx:end_idx]
                                    segment_max = np.max(np.abs(segment_data))
                                    
                                    # Calculate alpha based on segment amplitude
                                    segment_alpha = min(1.0, (segment_max / max_amplitude) ** sensitivity)
                                    segment_alpha = max(0.2, segment_alpha)  # Ensure minimum visibility
                                    
                                    # Create color with adjusted alpha
                                    segment_color = pg.mkColor(self.waveform_color)
                                    segment_color.setAlphaF(segment_alpha)
                                    segment_pen = pg.mkPen(segment_color, width=2)
                                    
                                    # Create segment indices for proper alignment
                                    x_data = np.arange(start_idx, end_idx)
                                    
                                    # Plot the segment
                                    segment_curve = waveform_plot.getPlotItem().plot(x_data, segment_data, pen=segment_pen)
                                    panel['plots'][f'segment_{i}'] = segment_curve
                        
                        # Check for frequency-based alpha effect
                        elif hasattr(self, 'frequency_alpha_check') and self.frequency_alpha_check.isChecked():
                            # Remove previous frequency band curves
                            for key in list(panel['plots'].keys()):
                                if key.startswith('freq_band_'):
                                    waveform_plot.getPlotItem().removeItem(panel['plots'][key])
                                    del panel['plots'][key]
                            
                            # Hide main waveform curve
                            waveform_curve.hide()
                            
                            # Perform FFT to get frequency content
                            if len(waveform_data) > 0:
                                fft_size = min(1024, len(waveform_data))
                                fft_data = np.fft.rfft(waveform_data[:fft_size])
                                fft_freq = np.fft.rfftfreq(fft_size, 1.0/self.audio_processor.sample_rate)
                                fft_mag = np.abs(fft_data)
                                
                                # Define frequency bands
                                bands = [
                                    (0, 200, "Bass"),      # 0-200 Hz (Bass)
                                    (200, 2000, "Mid"),   # 200-2000 Hz (Midrange)
                                    (2000, 20000, "High") # 2000-20000 Hz (Treble)
                                ]
                                
                                # Calculate energy in each band
                                band_energy = []
                                for low_freq, high_freq, _ in bands:
                                    band_indices = np.where((fft_freq >= low_freq) & (fft_freq <= high_freq))[0]
                                    if len(band_indices) > 0:
                                        band_energy.append(np.sum(fft_mag[band_indices]) / len(band_indices))
                                    else:
                                        band_energy.append(0)
                                
                                # Normalize band energy
                                total_energy = np.sum(band_energy) + 1e-10  # Avoid division by zero
                                band_energy_norm = [e / total_energy for e in band_energy]
                                
                                # Create a curve for each frequency band
                                for i, ((low_freq, high_freq, name), energy) in enumerate(zip(bands, band_energy_norm)):
                                    # Alpha based on energy in this band
                                    band_alpha = min(1.0, energy * 3)  # Scale for visibility
                                    band_alpha = max(0.2, band_alpha)  # Ensure minimum visibility
                                    
                                    # Different color for each band
                                    if name == "Bass":
                                        band_color = pg.mkColor(255, 0, 0)  # Red for bass
                                    elif name == "Mid":
                                        band_color = pg.mkColor(0, 255, 0)  # Green for midrange
                                    else:  # High
                                        band_color = pg.mkColor(0, 0, 255)  # Blue for treble
                                    
                                    band_color.setAlphaF(band_alpha)
                                    band_pen = pg.mkPen(band_color, width=2)
                                    
                                    # Plot the band
                                    band_curve = waveform_plot.getPlotItem().plot(waveform_data, pen=band_pen)
                                    panel['plots'][f'freq_band_{i}'] = band_curve
                        else:
                            # No special effect, update the main waveform curve
                            # Remove any segment or frequency band curves
                            for key in list(panel['plots'].keys()):
                                if key.startswith('segment_') or key.startswith('freq_band_'):
                                    waveform_plot.getPlotItem().removeItem(panel['plots'][key])
                                    del panel['plots'][key]
                            
                            # Show and update the main waveform curve
                            waveform_curve.show()
                            waveform_curve.setData(waveform_data)
                        
                        # Update peak hold
                        if self.peak_hold_check.isChecked():
                            if panel['peak_data'] is None:
                                panel['peak_data'] = np.abs(waveform_data)
                            else:
                                # Decay existing peaks
                                decay_rate = 0.1 * (self.peak_decay_slider.value() / 10.0)
                                panel['peak_data'] *= (1.0 - decay_rate)
                                # Update with new peaks
                                panel['peak_data'] = np.maximum(panel['peak_data'], np.abs(waveform_data))
                            
                            # Update peak curve
                            if 'peak_curve' not in panel['plots']:
                                peak_curve = waveform_plot.getPlotItem().plot(pen=pg.mkPen('r', width=1))
                                panel['plots']['peak_curve'] = peak_curve
                            
                            # Set positive and negative peaks
                            panel['plots']['peak_curve'].setData(panel['peak_data'] * np.sign(waveform_data))
                        elif 'peak_curve' in panel['plots']:
                            # Remove peak curve if disabled
                            waveform_plot.getPlotItem().removeItem(panel['plots']['peak_curve'])
                            del panel['plots']['peak_curve']
                            panel['peak_data'] = None
                        
                        # Update persistence effect
                        if self.persistence_check.isChecked():
                            # Add current waveform to persistence buffer
                            panel['persistence_data'].append(np.copy(waveform_data))
                            panel['persistence_alpha'].append(1.0)
                            
                            # Limit buffer size
                            max_persistence = 20
                            if len(panel['persistence_data']) > max_persistence:
                                panel['persistence_data'] = panel['persistence_data'][-max_persistence:]
                                panel['persistence_alpha'] = panel['persistence_alpha'][-max_persistence:]
                            
                            # Decay all persistence curves
                            decay_rate = 0.1 * (self.persistence_slider.value() / 10.0)
                            for i in range(len(panel['persistence_alpha'])):
                                panel['persistence_alpha'][i] *= (1.0 - decay_rate)
                            
                            # Remove old persistence curves
                            for key in list(panel['plots'].keys()):
                                if key.startswith('persistence_'):
                                    waveform_plot.getPlotItem().removeItem(panel['plots'][key])
                                    del panel['plots'][key]
                            
                            # Add new persistence curves
                            for i, (data, alpha) in enumerate(zip(panel['persistence_data'], panel['persistence_alpha'])):
                                if alpha > 0.05:  # Only show if alpha is significant
                                    color = pg.mkColor(self.waveform_color)
                                    color.setAlphaF(alpha * 0.7)
                                    persistence_curve = waveform_plot.getPlotItem().plot(
                                        data, pen=pg.mkPen(color, width=1))
                                    panel['plots'][f'persistence_{i}'] = persistence_curve
                        else:
                            # Remove persistence curves if disabled
                            for key in list(panel['plots'].keys()):
                                if key.startswith('persistence_'):
                                    waveform_plot.getPlotItem().removeItem(panel['plots'][key])
                                    del panel['plots'][key]
                            panel['persistence_data'] = []
                            panel['persistence_alpha'] = []
                    else:
                        # Fall back to the original method
                        # First get the plot item since waveform_plot might be a GraphicsLayoutWidget
                        if hasattr(waveform_plot, 'getPlotItem'):
                            plot_item = waveform_plot.getPlotItem()
                            if plot_item and plot_item.listDataItems():
                                waveform_curve = plot_item.listDataItems()[0]
                                waveform_curve.setData(waveform_data)
                        else:
                            # If it's already a PlotItem
                            if hasattr(waveform_plot, 'listDataItems') and waveform_plot.listDataItems():
                                waveform_curve = waveform_plot.listDataItems()[0]
                                waveform_curve.setData(waveform_data)
                
                # Update stats display if visible
                if panel['stats_widget'].isVisible():
                    # Calculate RMS
                    rms_val = np.sqrt(np.mean(np.square(waveform_data)))
                    if rms_val > 0:
                        rms_db = 20 * np.log10(rms_val)
                        panel['stats_labels']['rms'].setText(f"{rms_db:.1f} dB")
                    else:
                        panel['stats_labels']['rms'].setText("-∞ dB")
                    
                    # Calculate peak
                    peak_val = np.max(np.abs(waveform_data))
                    if peak_val > 0:
                        peak_db = 20 * np.log10(peak_val)
                        panel['stats_labels']['peak'].setText(f"{peak_db:.1f} dB")
                    else:
                        panel['stats_labels']['peak'].setText("-∞ dB")
                    
                    # Calculate crest factor
                    if rms_val > 0:
                        crest_factor = peak_val / rms_val
                        crest_db = 20 * np.log10(crest_factor)
                        panel['stats_labels']['crest'].setText(f"{crest_db:.1f} dB")
                    else:
                        panel['stats_labels']['crest'].setText("0 dB")
            
            elif viz_type == "Spectrogram" and spectrum_data is not None:
                if "Spectrogram" in panel['plots']:
                    spectrogram_plot = panel['plots']["Spectrogram"]
                    # Check if the plot has the spectrogram_img attribute
                    if hasattr(spectrogram_plot, 'spectrogram_img'):
                        spectrogram_plot.spectrogram_img.setImage(
                            self.spectrogram_buffer,
                            autoLevels=False
                        )
            
            elif viz_type == "Spectrum" and spectrum_data is not None:
                if "Spectrum" in panel['plots']:
                    spectrum_plot = panel['plots']["Spectrum"]
                    
                    # Apply smoothing if enabled
                    smoothed_spectrum = spectrum_data
                    smooth_factor = self.spectrum_smooth_slider.value()
                    if smooth_factor > 0:
                        kernel_size = 2 * smooth_factor + 1
                        kernel = np.ones(kernel_size) / kernel_size
                        smoothed_spectrum = np.convolve(spectrum_data, kernel, mode='same')
                    
                    if hasattr(spectrum_plot, 'spectrum_curve'):
                        spectrum_plot.spectrum_curve.setData(self.fft_freqs, smoothed_spectrum)
                        
                        # Update peak hold
                        if self.spectrum_peak_hold_check.isChecked():
                            if 'spectrum_peak_data' not in panel:
                                panel['spectrum_peak_data'] = np.copy(smoothed_spectrum)
                            else:
                                # Decay existing peaks
                                decay_rate = 0.1 * (self.spectrum_peak_decay_slider.value() / 10.0)
                                panel['spectrum_peak_data'] -= decay_rate
                                # Update with new peaks
                                panel['spectrum_peak_data'] = np.maximum(panel['spectrum_peak_data'], smoothed_spectrum)
                            
                            # Update peak curve
                            if 'spectrum_peak_curve' not in panel['plots']:
                                peak_curve = spectrum_plot.getPlotItem().plot(pen=pg.mkPen('r', width=1))
                                panel['plots']['spectrum_peak_curve'] = peak_curve
                            
                            panel['plots']['spectrum_peak_curve'].setData(self.fft_freqs, panel['spectrum_peak_data'])
                        elif 'spectrum_peak_curve' in panel['plots']:
                            # Remove peak curve if disabled
                            spectrum_plot.getPlotItem().removeItem(panel['plots']['spectrum_peak_curve'])
                            del panel['plots']['spectrum_peak_curve']
                            if 'spectrum_peak_data' in panel:
                                del panel['spectrum_peak_data']
                                
                        # Show frequency bands if enabled
                        if self.show_bands_check.isChecked():
                            # Define frequency bands (Hz)
                            bands = {
                                'Sub-bass': (20, 60),
                                'Bass': (60, 250),
                                'Low-mid': (250, 500),
                                'Mid': (500, 2000),
                                'Upper-mid': (2000, 4000),
                                'Presence': (4000, 6000),
                                'Brilliance': (6000, 20000)
                            }
                            
                            # Show bands as colored regions
                            for band_name, (low_freq, high_freq) in bands.items():
                                band_key = f'band_{band_name}'
                                
                                # Find band energy
                                low_idx = np.argmin(np.abs(self.fft_freqs - low_freq))
                                high_idx = np.argmin(np.abs(self.fft_freqs - high_freq))
                                band_energy = np.mean(smoothed_spectrum[low_idx:high_idx+1])
                                
                                # Create or update band region
                                if band_key not in panel['plots']:
                                    # Create a semi-transparent region for this band
                                    color = pg.mkColor('b')
                                    color.setAlphaF(0.2)
                                    band_region = pg.LinearRegionItem([low_freq, high_freq], 
                                                                    movable=False, 
                                                                    brush=color)
                                    spectrum_plot.getPlotItem().addItem(band_region)
                                    panel['plots'][band_key] = band_region
                                
                                # Adjust alpha based on energy
                                if band_key in panel['plots']:
                                    # Calculate alpha based on energy relative to min/max dB
                                    min_db = self.spectrum_min_db_spin.value()
                                    alpha = (band_energy - min_db) / (-min_db)
                                    alpha = max(0.1, min(0.5, alpha))
                                    
                                    color = pg.mkColor(f'#{hash(band_name) % 0xFFFFFF:06x}')
                                    color.setAlphaF(alpha)
                                    panel['plots'][band_key].setBrush(color)
                        else:
                            # Remove band regions if disabled
                            for key in list(panel['plots'].keys()):
                                if key.startswith('band_'):
                                    spectrum_plot.getPlotItem().removeItem(panel['plots'][key])
                                    del panel['plots'][key]
                    else:
                        # Fall back to the original method
                        spectrum_curve = spectrum_plot.listDataItems()[0]
                        spectrum_curve.setData(self.fft_freqs, smoothed_spectrum)
                    
                    # Update stats display if visible
                    if panel['stats_widget'].isVisible():
                        # Calculate average level
                        avg_level = np.mean(smoothed_spectrum)
                        panel['stats_labels']['rms'].setText(f"{avg_level:.1f} dB")
                        
                        # Calculate peak frequency
                        peak_idx = np.argmax(smoothed_spectrum)
                        peak_freq = self.fft_freqs[peak_idx]
                        peak_level = smoothed_spectrum[peak_idx]
                        panel['stats_labels']['peak'].setText(f"{peak_freq:.0f} Hz ({peak_level:.1f} dB)")
                        
                        # Calculate spectral centroid
                        if np.sum(smoothed_spectrum) > 0:
                            centroid = np.sum(self.fft_freqs * smoothed_spectrum) / np.sum(smoothed_spectrum)
                            panel['stats_labels']['crest'].setText(f"{centroid:.0f} Hz")
                        else:
                            panel['stats_labels']['crest'].setText("N/A")
                    
            # Update the output window if it's visible
            if self.output_window and self.output_window.isVisible():
                self.output_window.update_visualizations(waveform_data, spectrum_data)
            
            # Only update analysis if the method exists (don't reference analysis_panel to avoid errors)
            if hasattr(self, 'update_audio_analysis'):
                try:
                    self.update_audio_analysis(waveform_data, spectrum_data)
                except Exception as e:
                    # Silently ignore errors in the analysis update
                    pass
    
    def toggle_settings_panel(self):
        """Toggle the visibility of the settings panel."""
        self.settings_panel.setVisible(not self.settings_panel.isVisible())
        
    def toggle_analysis_panel(self):
        """Toggle the visibility of the analysis panel."""
        if self.analysis_button.isChecked():
            self.analysis_panel.setVisible(True)
        else:
            self.analysis_panel.setVisible(False)
    
    def update_audio_analysis(self, waveform, spectrum):
        """Update audio analysis metrics."""
        if waveform is None or len(waveform) == 0:
            return
            
        # Calculate peak level (in dB)
        peak = np.max(np.abs(waveform))
        peak_db = 20 * np.log10(peak + 1e-10)
        peak_db = max(-60, min(0, peak_db))  # Clamp between -60 and 0 dB
        
        # Update peak meter and label
        self.peak_meter.setValue(int(peak_db))
        self.peak_label.setText(f"{peak_db:.1f} dB")
        
        # Calculate RMS level (in dB)
        rms = np.sqrt(np.mean(np.square(waveform)))
        rms_db = 20 * np.log10(rms + 1e-10)
        rms_db = max(-60, min(0, rms_db))  # Clamp between -60 and 0 dB
        
        # Update RMS meter and label
        self.rms_meter.setValue(int(rms_db))
        self.rms_label.setText(f"{rms_db:.1f} dB")
        
        # Calculate crest factor (peak / RMS)
        if rms > 0:
            crest_factor = peak / rms
            crest_factor_db = 20 * np.log10(crest_factor)
            self.crest_factor_label.setText(f"{crest_factor:.2f} ({crest_factor_db:.1f} dB)")
        
        # Calculate spectral centroid if spectrum data is available
        if spectrum is not None and len(spectrum) > 0:
            # Convert from dB back to linear scale
            linear_spectrum = 10 ** (spectrum / 20)
            
            # Calculate frequency bins
            freq_step = self.audio_processor.sample_rate / (self.audio_processor.chunk_size)
            frequencies = np.arange(len(spectrum)) * freq_step
            
            # Calculate spectral centroid (weighted average of frequencies)
            centroid = np.sum(frequencies * linear_spectrum) / (np.sum(linear_spectrum) + 1e-10)
            
            # Display in Hz or kHz depending on the value
            if centroid >= 1000:
                self.spectral_centroid_label.setText(f"{centroid/1000:.2f} kHz")
            else:
                self.spectral_centroid_label.setText(f"{centroid:.0f} Hz")
        
        # Count zero crossings (rough indicator of "brightness")
        zero_crossings = np.sum(np.diff(np.signbit(waveform)))
        self.zero_crossings_label.setText(f"{zero_crossings}")
    
    def save_preset(self):
        """Save current settings as a preset."""
        preset_name = self.preset_name_edit.text().strip()
        
        if not preset_name:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please enter a preset name.")
            return
        
        # Create preset data
        preset_data = {
            "waveform": {
                "color": self.waveform_color.name(),
                "width": self.waveform_width_slider.value(),
                "fill": self.waveform_fill_check.isChecked(),
                "amplitude_scale": self.amplitude_scale_slider.value()
            },
            "spectrogram": {
                "colormap": self.colormap_combo.currentText(),
                "min_db": self.min_db_spin.value(),
                "max_db": self.max_db_spin.value(),
                "min_freq": self.min_freq_spin.value(),
                "max_freq": self.max_freq_spin.value(),
                "time_range": self.time_range_slider.value()
            },
            "bass_meter": {
                "color": self.bass_meter_color.name(),
                "min_freq": self.bass_min_freq_spin.value(),
                "max_freq": self.bass_max_freq_spin.value(),
                "sensitivity": self.bass_sensitivity_slider.value()
            },
            "panel_count": self.panel_count_combo.currentIndex() + 1,
            "panel_types": [panel['combo'].currentText() for panel in self.viz_panels]
        }
        
        # Ensure presets directory exists
        os.makedirs(self.presets_dir, exist_ok=True)
        
        # Save to file
        preset_path = os.path.join(self.presets_dir, f"{preset_name}.json")
        
        with open(preset_path, 'w') as f:
            json.dump(preset_data, f, indent=4)
        
        # Update preset list
        self.populate_preset_list()
        
        # Select the newly added preset
        items = self.preset_list.findItems(preset_name, Qt.MatchExactly)
        if items:
            self.preset_list.setCurrentItem(items[0])
            
        # Provide feedback
        self.statusBar().showMessage(f"Preset '{preset_name}' saved.", 3000)
    
    def load_preset(self, item):
        """Load the selected preset."""
        preset_name = item.text()
        self._load_preset_by_name(preset_name)
    
    def load_selected_preset(self):
        """Load the currently selected preset."""
        selected_items = self.preset_list.selectedItems()
        
        if not selected_items:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select a preset to load.")
            return
        
        preset_name = selected_items[0].text()
        self._load_preset_by_name(preset_name)
    
    def _load_preset_by_name(self, preset_name):
        """Load a preset by its name."""
        preset_path = os.path.join(self.presets_dir, f"{preset_name}.json")
        
        if not os.path.exists(preset_path):
            QtWidgets.QMessageBox.warning(self, "Warning", f"Preset '{preset_name}' not found.")
            return
        
        try:
            with open(preset_path, 'r') as f:
                preset_data = json.load(f)
            
            # Apply panel configuration first to ensure panels and visualizations exist
            if "panel_count" in preset_data:
                new_count = preset_data["panel_count"]
                if new_count != self.current_num_panels:
                    self.panel_count_combo.setCurrentIndex(new_count - 1)
                    self.update_panel_count(new_count - 1)
            
            # Apply panel types
            if "panel_types" in preset_data:
                panel_types = preset_data["panel_types"]
                for i, panel_type in enumerate(panel_types):
                    if i < len(self.viz_panels):
                        combo = self.viz_panels[i]['combo']
                        index = combo.findText(panel_type)
                        if index >= 0:
                            combo.setCurrentIndex(index)
                            # Force the visualization to update
                            self.change_panel_visualization(i, panel_type)
            
            # Wait a moment for visualizations to initialize
            QtCore.QCoreApplication.processEvents()
            
            # Apply waveform settings
            waveform = preset_data.get("waveform", {})
            if waveform:
                if "color" in waveform:
                    self.waveform_color = QColor(waveform["color"])
                    self.set_button_color(self.waveform_color_btn, self.waveform_color)
                if "width" in waveform:
                    self.waveform_width_slider.setValue(waveform["width"])
                if "fill" in waveform:
                    self.waveform_fill_check.setChecked(waveform["fill"])
                if "amplitude_scale" in waveform:
                    self.amplitude_scale_slider.setValue(waveform["amplitude_scale"])
                self.update_waveform_settings()
            
            # Apply spectrogram settings
            spectrogram = preset_data.get("spectrogram", {})
            if spectrogram:
                if "colormap" in spectrogram:
                    index = self.colormap_combo.findText(spectrogram["colormap"])
                    if index >= 0:
                        self.colormap_combo.setCurrentIndex(index)
                if "min_db" in spectrogram:
                    self.min_db_spin.setValue(spectrogram["min_db"])
                if "max_db" in spectrogram:
                    self.max_db_spin.setValue(spectrogram["max_db"])
                if "min_freq" in spectrogram:
                    self.min_freq_spin.setValue(spectrogram["min_freq"])
                if "max_freq" in spectrogram:
                    self.max_freq_spin.setValue(spectrogram["max_freq"])
                if "time_range" in spectrogram:
                    self.time_range_slider.setValue(spectrogram["time_range"])
                    self.update_time_range()
                self.update_spectrogram_settings()
            
            # Apply bass meter settings
            bass_meter = preset_data.get("bass_meter", {})
            if bass_meter:
                if "color" in bass_meter:
                    self.bass_meter_color = QColor(bass_meter["color"])
                    self.set_button_color(self.bass_meter_color_btn, self.bass_meter_color)
                if "min_freq" in bass_meter:
                    self.bass_min_freq_spin.setValue(bass_meter["min_freq"])
                if "max_freq" in bass_meter:
                    self.bass_max_freq_spin.setValue(bass_meter["max_freq"])
                if "sensitivity" in bass_meter:
                    self.bass_sensitivity_slider.setValue(bass_meter["sensitivity"])
                self.update_bass_meter_settings()
            
            # Provide feedback
            self.statusBar().showMessage(f"Preset '{preset_name}' loaded.", 3000)
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            QtWidgets.QMessageBox.warning(self, "Error", f"Failed to load preset: {str(e)}\n\nDetails: {error_details}")
    
    def delete_preset(self):
        """Delete the selected preset."""
        selected_items = self.preset_list.selectedItems()
        
        if not selected_items:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select a preset to delete.")
            return
        
        preset_name = selected_items[0].text()
        preset_path = os.path.join(self.presets_dir, f"{preset_name}.json")
        
        # Confirm deletion
        reply = QtWidgets.QMessageBox.question(
            self, 
            "Confirm Deletion",
            f"Are you sure you want to delete the preset '{preset_name}'?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            try:
                os.remove(preset_path)
                self.populate_preset_list()
                self.statusBar().showMessage(f"Preset '{preset_name}' deleted.", 3000)
            except Exception as e:
                QtWidgets.QMessageBox.warning(self, "Error", f"Failed to delete preset: {str(e)}")
    
    def toggle_presets_panel(self):
        """Toggle the visibility of the presets panel."""
        self.presets_panel.setVisible(not self.presets_panel.isVisible())
        if self.presets_panel.isVisible():
            self.populate_preset_list()
    
    def populate_preset_list(self):
        """Populate the preset list with saved presets."""
        self.preset_list.clear()
        
        # Ensure presets directory exists
        os.makedirs(self.presets_dir, exist_ok=True)
        
        # Get all preset files
        preset_files = glob.glob(os.path.join(self.presets_dir, "*.json"))
        
        # Add each preset to the list
        for preset_file in preset_files:
            preset_name = os.path.basename(preset_file).replace('.json', '')
            self.preset_list.addItem(preset_name)
    
    def toggle_recording(self):
        """Toggle recording state to capture visualization frames."""
        if not self.is_capturing:
            QtWidgets.QMessageBox.warning(
                self, "Recording Error", 
                "Cannot start recording without active audio capture.\n"
                "Please start audio capture first."
            )
            self.record_button.setChecked(False)
            return
            
        if not self.is_recording:
            # Start recording
            self.is_recording = True
            self.recorded_frames = []
            self.record_button.setText("Stop Recording")
            self.statusBar().showMessage("Recording started")
        else:
            # Stop recording
            self.is_recording = False
            self.record_button.setText("Record")
            
            # If frames were captured, offer to save
            if len(self.recorded_frames) > 0:
                self.statusBar().showMessage(f"Recording stopped. Captured {len(self.recorded_frames)} frames.")
                
                reply = QtWidgets.QMessageBox.question(
                    self, "Save Recording", 
                    f"Recording completed with {len(self.recorded_frames)} frames.\n"
                    "Would you like to save this recording?",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
                )
                
                if reply == QtWidgets.QMessageBox.Yes:
                    self.save_recording()
            else:
                self.statusBar().showMessage("Recording stopped. No frames captured.")
    
    def capture_visualization_frame(self):
        """Capture the current visualization as a frame for recording."""
        if not self.is_recording:
            return
            
        # Create a composite image of both visualizations
        waveform_img = self.capture_widget_image(self.waveform_plot)
        spectrogram_img = self.capture_widget_image(self.spectrogram_plot)
        
        # Store as a tuple for later processing
        self.recorded_frames.append((waveform_img, spectrogram_img))
    
    def capture_widget_image(self, widget):
        """Capture an image of a widget."""
        image = QImage(widget.size(), QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        
        painter = QPainter(image)
        widget.render(painter)
        painter.end()
        
        return image
    
    def save_recording(self):
        """Save the recorded frames as a series of images."""
        if len(self.recorded_frames) == 0:
            return
            
        # Create a timestamped directory for this recording
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        recording_dir = os.path.join(self.exports_dir, f"recording_{timestamp}")
        os.makedirs(recording_dir, exist_ok=True)
        
        # Create subdirectories
        waveform_dir = os.path.join(recording_dir, "waveform")
        spectrogram_dir = os.path.join(recording_dir, "spectrogram")
        os.makedirs(waveform_dir, exist_ok=True)
        os.makedirs(spectrogram_dir, exist_ok=True)
        
        # Set up progress dialog
        progress = QtWidgets.QProgressDialog(
            "Saving frames...", "Abort", 0, len(self.recorded_frames), self
        )
        progress.setWindowModality(Qt.WindowModal)
        
        # Save each frame
        aborted = False
        for i, (waveform_img, spectrogram_img) in enumerate(self.recorded_frames):
            if progress.wasCanceled():
                aborted = True
                break
                
            # Save waveform
            waveform_path = os.path.join(waveform_dir, f"frame_{i:04d}.png")
            waveform_img.save(waveform_path)
            
            # Save spectrogram
            spectrogram_path = os.path.join(spectrogram_dir, f"frame_{i:04d}.png")
            spectrogram_img.save(spectrogram_path)
            
            progress.setValue(i)
        
        progress.setValue(len(self.recorded_frames))
        
        if aborted:
            self.statusBar().showMessage("Recording save operation aborted.")
        else:
            # Create an HTML index file for easy viewing
            self.create_recording_index(recording_dir)
            self.statusBar().showMessage(f"Recording saved to {recording_dir}")
            
            # Ask if user wants to open the folder
            reply = QtWidgets.QMessageBox.question(
                self, "Open Export Folder", 
                "Would you like to open the export folder?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            
            if reply == QtWidgets.QMessageBox.Yes:
                # Open folder in Finder
                QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(recording_dir))
    
    def create_recording_index(self, recording_dir):
        """Create an HTML index file for browsing the recording frames."""
        index_path = os.path.join(recording_dir, "index.html")
        
        with open(index_path, 'w') as f:
            f.write(f"""<!DOCTYPE html>
<html>
<head>
    <title>Spectograma Recording</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        .frame-container {{ display: flex; margin-bottom: 20px; border: 1px solid #ddd; padding: 10px; }}
        .frame-container img {{ max-width: 45%; margin: 10px; }}
        .controls {{ margin: 20px 0; }}
        button {{ padding: 5px 10px; margin-right: 10px; }}
    </style>
</head>
<body>
    <h1>Spectograma Recording</h1>
    <p>Recorded on {datetime.datetime.now().strftime("%Y-%m-%d at %H:%M:%S")}</p>
    
    <div class="controls">
        <button id="prev">Previous</button>
        <button id="play">Play</button>
        <button id="next">Next</button>
        <span id="frame-counter">Frame: 1/{len(self.recorded_frames)}</span>
    </div>
    
    <div id="viewer" class="frame-container">
        <img id="waveform" src="waveform/frame_0000.png" alt="Waveform">
        <img id="spectrogram" src="spectrogram/frame_0000.png" alt="Spectrogram">
    </div>
    
    <script>
        let currentFrame = 0;
        const totalFrames = {len(self.recorded_frames)};
        let isPlaying = false;
        let playInterval;
        
        const frameCounter = document.getElementById('frame-counter');
        const waveformImg = document.getElementById('waveform');
        const spectrogramImg = document.getElementById('spectrogram');
        const playBtn = document.getElementById('play');
        
        function updateFrame() {{
            waveformImg.src = `waveform/frame_${{currentFrame.toString().padStart(4, '0')}}.png`;
            spectrogramImg.src = `spectrogram/frame_${{currentFrame.toString().padStart(4, '0')}}.png`;
            frameCounter.textContent = `Frame: ${{currentFrame + 1}}/${{totalFrames}}`;
        }}
        
        document.getElementById('prev').addEventListener('click', () => {{
            if (isPlaying) togglePlay();
            currentFrame = (currentFrame - 1 + totalFrames) % totalFrames;
            updateFrame();
        }});
        
        document.getElementById('next').addEventListener('click', () => {{
            if (isPlaying) togglePlay();
            currentFrame = (currentFrame + 1) % totalFrames;
            updateFrame();
        }});
        
        function togglePlay() {{
            isPlaying = !isPlaying;
            if (isPlaying) {{
                playBtn.textContent = 'Pause';
                playInterval = setInterval(() => {{
                    currentFrame = (currentFrame + 1) % totalFrames;
                    updateFrame();
                }}, 33); // ~30fps
            }} else {{
                playBtn.textContent = 'Play';
                clearInterval(playInterval);
            }}
        }}
        
        playBtn.addEventListener('click', togglePlay);
    </script>
</body>
</html>
""")

    def set_button_color(self, button, color):
        """Set the color of a button."""
        button.setStyleSheet(f"background-color: {color.name()}; border: 1px solid black;")

    def choose_waveform_color(self):
        """Open a color dialog to choose the waveform color."""
        color = QtWidgets.QColorDialog.getColor()
        if color.isValid():
            self.waveform_color = color
            self.set_button_color(self.waveform_color_btn, color)
            self.waveform_curve.setPen(pg.mkPen(color, width=self.waveform_width_slider.value()))

    def update_waveform_settings(self):
        """Update all waveform visualizations with the current settings."""
        try:
            # Get current settings
            color = self.waveform_color
            pen_width = self.waveform_width_slider.value()
            fill = self.waveform_fill_check.isChecked()
            amplitude_scale = self.amplitude_scale_slider.value() / 10.0  # Convert 1-20 to scale of 0.1-2.0
            normalization = self.normalization_combo.currentText()
            sensitivity = self.sensitivity_slider.value() / 10.0  # Convert 1-20 to scale of 0.1-2.0
            time_range_percent = self.time_range_slider.value()
            show_grid = self.grid_lines_check.isChecked()
            show_zero_line = self.zero_line_check.isChecked()
            
            # Create pen and brush
            pen = pg.mkPen(color, width=pen_width)
            brush = pg.mkBrush(color) if fill else None
            
            # Store settings for audio processing
            self.waveform_settings = {
                'amplitude_scale': amplitude_scale,
                'normalization': normalization,
                'sensitivity': sensitivity,
                'time_range_percent': time_range_percent
            }
            
            # Update all waveform visualizations
            for panel in self.viz_panels:
                if "Waveform" in panel['plots']:
                    try:
                        waveform_plot = panel['plots']["Waveform"]
                        if waveform_plot and waveform_plot.getPlotItem():
                            # Update plot visuals
                            plot_item = waveform_plot.getPlotItem()
                            
                            # Apply grid settings
                            plot_item.showGrid(x=show_grid, y=show_grid, alpha=0.3)
                            
                            # Add or update zero reference line
                            if show_zero_line:
                                if not hasattr(waveform_plot, 'zero_line'):
                                    waveform_plot.zero_line = pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen('w', width=1, style=Qt.DashLine))
                                    plot_item.addItem(waveform_plot.zero_line)
                                else:
                                    if waveform_plot.zero_line not in plot_item.items:
                                        plot_item.addItem(waveform_plot.zero_line)
                            elif hasattr(waveform_plot, 'zero_line') and waveform_plot.zero_line in plot_item.items:
                                plot_item.removeItem(waveform_plot.zero_line)
                            
                            # Update the curve settings
                            data_items = plot_item.listDataItems()
                            if data_items and len(data_items) > 0:
                                curve = data_items[0]
                                curve.setPen(pen)
                                if hasattr(curve, 'setBrush'):
                                    curve.setBrush(brush)
                    except Exception as e:
                        print(f"Error updating waveform in panel: {str(e)}")
                        continue
                        
            # If audio processor exists, update its settings
            if hasattr(self, 'audio_processor'):
                self.audio_processor.waveform_settings = self.waveform_settings
                
        except Exception as e:
            print(f"Error updating waveform settings: {str(e)}")

    def choose_band_color(self, band_type):
        """Open a color dialog to choose a frequency band color."""
        color = QtWidgets.QColorDialog.getColor()
        if color.isValid():
            if band_type == "bass":
                self.bass_color = color
                self.set_button_color(self.bass_color_btn, color)
                self.bass_region.setBrush(pg.mkBrush(color.red(), color.green(), color.blue(), 30))
            elif band_type == "mid":
                self.mid_color = color
                self.set_button_color(self.mid_color_btn, color)
                self.mid_region.setBrush(pg.mkBrush(color.red(), color.green(), color.blue(), 30))
            elif band_type == "treble":
                self.treble_color = color
                self.set_button_color(self.treble_color_btn, color)
                self.treble_region.setBrush(pg.mkBrush(color.red(), color.green(), color.blue(), 30))

    def update_spectrogram_settings(self):
        """Update the spectrogram visualization with current settings."""
        # Get the selected colormap
        cmap_name = self.colormap_combo.currentText()
        colormap = pg.colormap.get(cmap_name)
        
        # Get dB range
        min_db = self.min_db_spin.value()
        max_db = self.max_db_spin.value()
        
        # Get frequency range
        min_freq = self.min_freq_spin.value()
        max_freq = self.max_freq_spin.value()
        
        # Update all spectrogram visualizations
        for panel in self.viz_panels:
            if "Spectrogram" in panel['plots']:
                spectrogram_plot = panel['plots']["Spectrogram"]
                if hasattr(spectrogram_plot, 'spectrogram_img'):
                    # Update colormap
                    spectrogram_plot.spectrogram_img.setLookupTable(colormap.getLookupTable(alpha=True))
                    # Update levels
                    spectrogram_plot.spectrogram_img.setLevels([min_db, max_db])
                    # Update y-axis range (frequency)
                    try:
                        spectrogram_plot.setYRange(min_freq, max_freq)
                    except ValueError:
                        # Fallback if the range is invalid
                        pass
        
        # Force a redraw of all spectrograms to apply settings immediately
        for panel in self.viz_panels:
            if "Spectrogram" in panel['plots']:
                panel['plots']["Spectrogram"].update()
        
        # Update the output window if it exists
        if self.output_window and self.output_window.isVisible():
            self.force_sync_output_window()

    def update_spectrum_settings(self):
        """Update all spectrum visualizations with the current settings."""
        try:
            # Get current settings
            freq_scale = self.freq_scale_combo.currentText()
            min_db = self.spectrum_min_db_spin.value()
            show_peaks = self.spectrum_peak_hold_check.isChecked()
            show_bands = self.show_bands_check.isChecked()
            
            # Update all spectrum visualizations
            for panel in self.viz_panels:
                if "Spectrum" in panel['plots']:
                    try:
                        spectrum_plot = panel['plots']["Spectrum"]
                        if spectrum_plot and hasattr(spectrum_plot, 'setYRange'):
                            # Set Y range
                            spectrum_plot.setYRange(min_db, 0)
                            
                            # Set X scale type
                            if freq_scale == "Logarithmic":
                                spectrum_plot.setLogMode(x=True, y=False)
                            else:
                                spectrum_plot.setLogMode(x=False, y=False)
                    except Exception as e:
                        print(f"Error updating spectrum in panel: {str(e)}")
                        continue
            
            # Update the output window if it exists
            if self.output_window and self.output_window.isVisible():
                self.force_sync_output_window()
                
        except Exception as e:
            print(f"Error updating spectrum settings: {str(e)}")
    
    def update_time_range(self):
        """Update the time range for spectrograms."""
        # Get the new time range
        time_range = self.time_range_slider.value()
        
        # Create a new buffer with the desired size
        sample_rate = self.audio_processor.sample_rate
        chunk_size = self.audio_processor.chunk_size
        updates_per_second = sample_rate / chunk_size
        new_buffer_size = int(time_range * updates_per_second)
        
        # Copy the old data if possible
        old_buffer = self.spectrogram_buffer
        new_buffer = np.zeros((new_buffer_size, len(self.fft_freqs)))
        
        # Copy as much of the old data as will fit
        copy_size = min(old_buffer.shape[0], new_buffer.shape[0])
        new_buffer[-copy_size:] = old_buffer[-copy_size:]
        
        # Update the buffer
        self.spectrogram_buffer = new_buffer
        self.buffer_size = new_buffer_size

    def setup_default_visualizations(self):
        """Initialize default visualization elements like curves and images."""
        # Create empty references for old-style visualization elements
        # These are kept for backward compatibility with existing methods
        self.waveform_curve = None
        self.waveform_plot = None
        self.spectrogram_img = None
        self.spectrogram_plot = None
        self.spectrum_curve = None
        
        # Create dictionaries to hold old visualizations
        self.top_plots = {}
        self.bottom_plots = {}
    
    def closeEvent(self, event):
        """Handle window close event to clean up resources."""
        self.update_timer.stop()
        self.audio_capture.stop_capture()
        super().closeEvent(event)

    def export_waveform(self):
        """Export the current waveform visualization as an image."""
        if not self.is_capturing:
            QtWidgets.QMessageBox.warning(
                self, "Export Error", 
                "Cannot export without active audio capture.\n"
                "Please start audio capture first."
            )
            return

        # Capture the waveform
        image = self.capture_widget_image(self.waveform_plot)

        # Get save path
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_path = os.path.join(self.exports_dir, f"waveform_{timestamp}.png")
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Waveform Image", default_path, "Images (*.png *.jpg)"
        )

        if file_path:
            image.save(file_path)
            self.statusBar().showMessage(f"Waveform exported to {file_path}")

    def export_spectrogram(self):
        """Export the current spectrogram visualization as an image."""
        if not self.is_capturing:
            QtWidgets.QMessageBox.warning(
                self, "Export Error", 
                "Cannot export without active audio capture.\n"
                "Please start audio capture first."
            )
            return

        # Capture the spectrogram
        image = self.capture_widget_image(self.spectrogram_plot)

        # Get save path
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_path = os.path.join(self.exports_dir, f"spectrogram_{timestamp}.png")
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Spectrogram Image", default_path, "Images (*.png *.jpg)"
        )

        if file_path:
            image.save(file_path)
            self.statusBar().showMessage(f"Spectrogram exported to {file_path}")

    def export_both(self):
        """Export both visualizations as a combined image."""
        if not self.is_capturing:
            QtWidgets.QMessageBox.warning(
                self, "Export Error", 
                "Cannot export without active audio capture.\n"
                "Please start audio capture first."
            )
            return

        # Capture both visualizations
        waveform_img = self.capture_widget_image(self.waveform_plot)
        spectrogram_img = self.capture_widget_image(self.spectrogram_plot)

        # Create a combined image
        combined_height = waveform_img.height() + spectrogram_img.height()
        combined_width = max(waveform_img.width(), spectrogram_img.width())

        combined_img = QImage(combined_width, combined_height, QImage.Format_ARGB32)
        combined_img.fill(Qt.white)

        painter = QPainter(combined_img)
        painter.drawImage(0, 0, waveform_img)
        painter.drawImage(0, waveform_img.height(), spectrogram_img)
        painter.end()

        # Get save path
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_path = os.path.join(self.exports_dir, f"spectograma_{timestamp}.png")
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Combined Image", default_path, "Images (*.png *.jpg)"
        )

        if file_path:
            combined_img.save(file_path)
            self.statusBar().showMessage(f"Combined visualization exported to {file_path}")

    def force_sync_output_window(self):
        """Force synchronization of the output window with the main app."""
        if not self.output_window or not self.output_window.isVisible():
            return
            
        # Reset and rebuild the output window
        self.output_window.clear_all_plots()
        
        # Print debug info
        print("Syncing output window...")
        print(f"Main app panels: {len(self.viz_panels)}")
        for i, panel in enumerate(self.viz_panels):
            viz_type = panel['combo'].currentText()
            print(f"Panel {i+1}: {viz_type}")
            
        # Sync spectrogram buffer
        self.output_window.spectrogram_buffer = self.spectrogram_buffer.copy() if hasattr(self, 'spectrogram_buffer') and self.spectrogram_buffer is not None else None
        
        # Force the sync operation with detailed logging
        result = self.output_window.sync_panel_configuration(self, True)
        print(f"Sync result: {result} plots created")
        
        # Get the latest audio data and update the output window immediately
        if self.is_capturing:
            audio_data = self.audio_capture.get_audio_chunk()
            if audio_data is not None:
                waveform_data, spectrum_data = self.audio_processor.process_audio(audio_data)
                if waveform_data is not None and spectrum_data is not None:
                    self.output_window.update_visualizations(waveform_data, spectrum_data)
                    print("Initial data sent to output window")
        
        # Update the status bar
        self.statusBar().showMessage("Output window synchronized", 3000)
    
    def sync_output_window_settings(self):
        """Sync all settings from main window to output window."""
        if not self.output_window or not self.output_window.isVisible():
            return
            
        # First, make sure the output window has the right panels
        self.output_window.sync_panel_configuration(self)

    def initialize_visualization_panels(self):
        """Initialize visualization panels based on the panel count."""
        # Clear existing panels first
        for i in reversed(range(self.viz_panel_container.count())):
            widget = self.viz_panel_container.widget(i)
            if widget:
                widget.deleteLater()
        
        # Initialize storage for panel settings and plots
        self.viz_panels = []
        
        # Get panel count
        panel_count = int(self.panel_count_combo.currentText())
        
        # Create panels
        for i in range(panel_count):
            # Create panel widget
            panel_widget = QtWidgets.QWidget()
            panel_layout = QtWidgets.QVBoxLayout(panel_widget)
            panel_layout.setContentsMargins(0, 0, 0, 0)
            
            # Create control bar for this panel
            control_bar = QtWidgets.QHBoxLayout()
            control_bar.setContentsMargins(5, 2, 5, 2)
            
            # Panel label
            panel_label = QtWidgets.QLabel(f"Panel {i+1}:")
            control_bar.addWidget(panel_label)
            
            # Visualization type selector
            viz_combo = QtWidgets.QComboBox()
            viz_combo.addItems(["Waveform", "Spectrum", "Spectrogram"])
            viz_combo.setCurrentText("Waveform" if i == 0 else "Spectrum" if i == 1 else "Spectrogram")
            viz_combo.currentTextChanged.connect(lambda text, panel_idx=i: self.change_visualization(panel_idx, text))
            control_bar.addWidget(viz_combo)
            
            # Panel-specific settings button
            settings_btn = QtWidgets.QPushButton("Settings")
            settings_btn.setFixedWidth(70)
            settings_btn.clicked.connect(lambda _, panel_idx=i: self.show_panel_settings(panel_idx))
            control_bar.addWidget(settings_btn)
            
            # Add stat display toggle
            stats_btn = QtWidgets.QPushButton("Stats")
            stats_btn.setFixedWidth(60)
            stats_btn.setCheckable(True)
            stats_btn.clicked.connect(lambda checked, panel_idx=i: self.toggle_stats_display(panel_idx, checked))
            control_bar.addWidget(stats_btn)
            
            # Add control bar to panel layout
            panel_layout.addLayout(control_bar)
            
            # Create plot widget based on visualization type
            plot_widget = pg.GraphicsLayoutWidget()
            plot_widget.setBackground('k')  # Black background
            panel_layout.addWidget(plot_widget, 1)  # Give plot stretch priority
            
            # Create stats display (hidden by default)
            stats_widget = QtWidgets.QWidget()
            stats_layout = QtWidgets.QHBoxLayout(stats_widget)
            stats_layout.setContentsMargins(5, 2, 5, 2)
            
            # RMS level
            stats_layout.addWidget(QtWidgets.QLabel("RMS:"))
            rms_label = QtWidgets.QLabel("-∞ dB")
            stats_layout.addWidget(rms_label)
            
            # Peak level
            stats_layout.addWidget(QtWidgets.QLabel("Peak:"))
            peak_label = QtWidgets.QLabel("-∞ dB")
            stats_layout.addWidget(peak_label)
            
            # Crest factor
            stats_layout.addWidget(QtWidgets.QLabel("Crest:"))
            crest_label = QtWidgets.QLabel("0 dB")
            stats_layout.addWidget(crest_label)
            
            stats_widget.setVisible(False)
            panel_layout.addWidget(stats_widget)
            
            # Add panel to container
            self.viz_panel_container.addWidget(panel_widget)
            
            # Store panel info
            self.viz_panels.append({
                'widget': panel_widget,
                'plot_widget': plot_widget,
                'stats_widget': stats_widget,
                'combo': viz_combo,
                'settings_btn': settings_btn,
                'stats_btn': stats_btn,
                'stats_labels': {
                    'rms': rms_label,
                    'peak': peak_label,
                    'crest': crest_label
                },
                'plots': {},
                'peak_data': None,
                'persistence_data': [],
                'persistence_alpha': []
            })
            
            # Initialize the plot for this panel
            self.update_visualization_type(i, viz_combo.currentText())
    
    def update_panel_count(self):
        """Update the number of visualization panels."""
        self.initialize_visualization_panels()
        
        # Update the output window if it exists and is visible
        if self.output_window and self.output_window.isVisible():
            self.force_sync_output_window()
    
    def update_visualization_type(self, panel_idx, viz_type):
        """Update the visualization type for a panel."""
        if panel_idx >= len(self.viz_panels):
            return
        
        panel = self.viz_panels[panel_idx]
        # Clear the current plot
        panel['plot_widget'].clear()
        
        # Set up the new visualization
        setup_func = self.viz_types[viz_type]
        setup_func(panel['plot_widget'], f"panel_{panel_idx}")
        
        # Store the plot reference
        panel['plots'][viz_type] = panel['plot_widget']
        
    def toggle_output_window(self):
        """Toggle the visibility of the clean output window."""
        if not self.output_window:
            self.output_window = OutputWindow(self)
            
        if self.output_window.isVisible():
            self.output_window.hide()
            self.sync_output_btn.setEnabled(False)
        else:
            self.output_window.show()
            self.sync_output_btn.setEnabled(True)
            # Apply current settings to output window
            self.force_sync_output_window()
    
class OutputWindow(QtWidgets.QMainWindow):
    """Clean output window that mirrors main application visualizations without controls."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Spectograma Output")
        self.resize(800, 600)
        
        # Create central widget and layout
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        
        # Add a title label
        title_label = QtWidgets.QLabel("Spectograma Output")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 16pt; font-weight: bold;")
        main_layout.addWidget(title_label)
        
        # Add status label to show configuration
        self.status_label = QtWidgets.QLabel("Not synchronized yet")
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)
        
        # Create splitter for visualizations
        self.viz_splitter = QtWidgets.QSplitter(Qt.Vertical)
        main_layout.addWidget(self.viz_splitter)
        
        # Store plot widgets
        self.plots = []
        self.spectrogram_buffer = None
    
    def clear_all_plots(self):
        """Clear all plots from the output window."""
        # Clear existing plots
        while self.viz_splitter.count() > 0:
            widget = self.viz_splitter.widget(0)  # Always remove the first widget
            if widget:
                widget.setParent(None)  # Remove from splitter
                widget.deleteLater()
        
        self.plots = []
        self.status_label.setText("Cleared all plots")
    
    def sync_panel_configuration(self, parent, debug=False):
        """Sync the panel configuration with the parent window."""
        if not parent:
            return 0
        
        # Clear existing plots first
        self.clear_all_plots()
        
        # Get the number of panels and panel types from parent
        num_panels = len(parent.viz_panels)
        status_text = f"Showing {num_panels} panel"
        if num_panels != 1:
            status_text += "s"
        
        # Report panel types
        panel_types = []
        
        # Create new panels that match the parent configuration
        for i in range(num_panels):
            panel = parent.viz_panels[i]
            combo = panel['combo']
            viz_type = combo.currentText()
            panel_types.append(viz_type)
            
            if debug:
                print(f"Creating {viz_type} panel for output window")
            
            # Create plot widget based on visualization type
            if viz_type == "Waveform":
                plot_widget = pg.PlotWidget()
                plot_widget.setTitle(f"Waveform {i+1}")
                plot_widget.setLabel('left', 'Amplitude')
                plot_widget.setLabel('bottom', 'Sample')
                plot_widget.setYRange(-parent.amplitude_scale_slider.value(), 
                                     parent.amplitude_scale_slider.value())
                
                # Create waveform curve with parent settings
                pen = pg.mkPen(parent.waveform_color, width=parent.waveform_width_slider.value())
                curve = plot_widget.plot(pen=pen)
                
                # Apply fill if enabled in parent
                if parent.waveform_fill_check.isChecked():
                    curve.setFillLevel(0)
                    curve.setFillBrush(pg.mkBrush(parent.waveform_color))
                
                self.plots.append({
                    'type': 'Waveform',
                    'widget': plot_widget,
                    'curve': curve,
                    'panel_id': i
                })
                
            elif viz_type == "Spectrogram":
                plot_widget = pg.PlotWidget()
                plot_widget.setTitle(f"Spectrogram {i+1}")
                plot_widget.setLabel('left', 'Frequency (Hz)')
                plot_widget.setLabel('bottom', 'Time (s)')
                
                # Create image item
                img = pg.ImageItem()
                plot_widget.addItem(img)
                
                # Apply parent's colormap
                cmap_name = parent.colormap_combo.currentText()
                colormap = pg.colormap.get(cmap_name)
                img.setLookupTable(colormap.getLookupTable(alpha=True))
                
                # Set frequency range
                min_freq = parent.min_freq_spin.value()
                max_freq = parent.max_freq_spin.value()
                plot_widget.setYRange(min_freq, max_freq)
                
                # Set dB range
                min_db = parent.min_db_spin.value()
                max_db = parent.max_db_spin.value()
                img.setLevels([min_db, max_db])
                
                self.plots.append({
                    'type': 'Spectrogram',
                    'widget': plot_widget,
                    'img': img,
                    'panel_id': i
                })
                
            elif viz_type == "Spectrum":
                plot_widget = pg.PlotWidget()
                plot_widget.setTitle(f"Spectrum {i+1}")
                plot_widget.setLabel('left', 'Magnitude (dB)')
                plot_widget.setLabel('bottom', 'Frequency (Hz)')
                
                # Log scale for frequency axis
                plot_widget.setLogMode(x=True)
                
                # Set initial range
                plot_widget.setYRange(-80, 0)  # dB range
                plot_widget.setXRange(np.log10(20), np.log10(20000))  # 20Hz to 20kHz
                
                # Add curve for spectrum
                pen = pg.mkPen('y', width=2)
                curve = plot_widget.plot(pen=pen)
                
                self.plots.append({
                    'type': 'Spectrum',
                    'widget': plot_widget,
                    'curve': curve,
                    'panel_id': i
                })
            
            # Add the widget to the splitter
            self.viz_splitter.addWidget(plot_widget)
        
        # Set equal sizes for all plots
        sizes = [100] * num_panels
        self.viz_splitter.setSizes(sizes)
        
        # Update status text with panel types
        status_text += ": " + ", ".join(panel_types)
        self.status_label.setText(status_text)
        
        return len(self.plots)
    
    def update_visualizations(self, waveform_data, spectrum_data):
        """Update all visualization panels with the latest audio data."""
        if waveform_data is None or spectrum_data is None:
            return
            
        # Update spectrogram buffer
        if spectrum_data is not None:
            if not hasattr(self, 'spectrogram_buffer'):
                self.spectrogram_buffer = np.zeros((self.parent().buffer_size, len(self.parent().fft_freqs)))
            self.spectrogram_buffer = np.roll(self.spectrogram_buffer, -1, axis=0)
            self.spectrogram_buffer[-1] = spectrum_data
            
        # Update each plot
        for plot_info in self.plots:
            if plot_info['type'] == 'Waveform' and waveform_data is not None:
                plot_info['curve'].setData(waveform_data)
                
            elif plot_info['type'] == 'Spectrogram' and spectrum_data is not None:
                plot_info['img'].setImage(
                    self.spectrogram_buffer,
                    autoLevels=False
                )
                
            elif plot_info['type'] == 'Spectrum' and spectrum_data is not None:
                # Calculate frequencies for x-axis
                if hasattr(self.parent(), 'fft_freqs'):
                    freqs = self.parent().fft_freqs
                    plot_info['curve'].setData(freqs, spectrum_data)
                    
    def setup_waveform_viz(self, plot_widget, panel_id):
        """Set up a waveform visualization in the given plot widget."""
        plot_widget.setLabel('left', 'Amplitude')
        plot_widget.setLabel('bottom', 'Sample')
        plot_widget.setYRange(-self.amplitude_scale_slider.value() if hasattr(self, 'amplitude_scale_slider') else 1, 
                             self.amplitude_scale_slider.value() if hasattr(self, 'amplitude_scale_slider') else 1)
        
        # Add a curve for the waveform
        pen = pg.mkPen(self.waveform_color, width=self.waveform_width_slider.value() if hasattr(self, 'waveform_width_slider') else 2)
        curve = plot_widget.plot(pen=pen)
        
        # Add waveform fill if setting is enabled
        if hasattr(self, 'waveform_fill_check') and self.waveform_fill_check.isChecked():
            curve.setFillLevel(0)
            curve.setFillBrush(pg.mkBrush(self.waveform_color))
        
        # Store the curve reference on the plot widget for later updates
        plot_widget.waveform_curve = curve
        
    def setup_spectrogram_viz(self, plot_widget, name):
        """Set up a spectrogram visualization."""
        # Configure plot
        plot_widget.setLabel('bottom', 'Time', 's')
        plot_widget.setLabel('left', 'Frequency', 'Hz')
        plot_widget.setLimits(xMin=0)
        
        # Set log scale for frequency axis
        plot_widget.setLogMode(y=True)
        
        # Store the log-scaled frequency bins if available
        try:
            if not hasattr(self, 'log_freqs'):
                # Convert to logarithmic scale for better visualization
                self.log_freqs = np.log10(self.fft_freqs)
        except (AttributeError, ValueError):
            # Fallback if logarithmic conversion fails
            pass
            
        # Create a dummy spectrogram data array to initialize the image item
        dummy_data = np.zeros((len(self.fft_freqs), self.buffer_size))
        
        # Create spectrogram image
        spectrogram_img = pg.ImageItem()
        spectrogram_img.setImage(dummy_data)  # No transpose - we're using the correct orientation
        
        # Set position and scale for the image
        rect = QtCore.QRectF(0, 0, self.buffer_size, len(self.fft_freqs))
        spectrogram_img.setRect(rect)
        
        # Add the image to the plot
        plot_widget.addItem(spectrogram_img)
        
        # Apply current settings
        if hasattr(self, 'colormap_combo'):
            # Get the selected colormap
            cmap_name = self.colormap_combo.currentText()
            colormap = pg.colormap.get(cmap_name)
            # Set colormap
            spectrogram_img.setLookupTable(colormap.getLookupTable(alpha=True))
            
            # Apply dB range
            min_db = self.min_db_spin.value()
            max_db = self.max_db_spin.value()
            spectrogram_img.setLevels([min_db, max_db])
            
            # Apply frequency range
            min_freq = self.min_freq_spin.value()
            max_freq = self.max_freq_spin.value()
            try:
                plot_widget.setYRange(np.log10(min_freq), np.log10(max_freq))
            except ValueError:
                # Fallback if the range is invalid
                pass
        
        # Store reference to the image item as an attribute of the plot widget
        plot_widget.spectrogram_img = spectrogram_img
        
        # Store in plots dictionary
        for panel in self.viz_panels:
            if 'plots' in panel and name == "Spectrogram":
                panel['plots'][name] = plot_widget
        
        # Return for immediate use if needed
        return plot_widget
        
    def setup_spectrum_viz(self, plot_widget, panel_id):
        """Set up a spectrum visualization in the given plot widget."""
        plot_widget.setLabel('left', 'Magnitude (dB)')
        plot_widget.setLabel('bottom', 'Frequency (Hz)')
        
        # Log scale for frequency axis
        plot_widget.setLogMode(x=True)
        
        # Set initial range
        plot_widget.setYRange(-80, 0)  # dB range
        plot_widget.setXRange(np.log10(20), np.log10(20000))  # 20Hz to 20kHz
        
        # Add curve for spectrum
        pen = pg.mkPen('y', width=2)
        curve = plot_widget.plot(pen=pen)
        
        # Store the curve reference on the plot widget for later updates
        plot_widget.spectrum_curve = curve

    def toggle_stats_display(self, panel_idx, checked):
        """Toggle the visibility of the stats display for the given panel."""
        if panel_idx < len(self.viz_panels):
            self.viz_panels[panel_idx]['stats_widget'].setVisible(checked)

    def update_spectrum_settings(self):
        """Update all spectrum visualizations with the current settings."""
        try:
            # Get current settings
            freq_scale = self.freq_scale_combo.currentText()
            min_db = self.spectrum_min_db_spin.value()
            show_peaks = self.spectrum_peak_hold_check.isChecked()
            show_bands = self.show_bands_check.isChecked()
            
            # Update all spectrum visualizations
            for panel in self.viz_panels:
                if "Spectrum" in panel['plots']:
                    try:
                        spectrum_plot = panel['plots']["Spectrum"]
                        if spectrum_plot and spectrum_plot.getPlotItem():
                            plot_item = spectrum_plot.getPlotItem()
                            
                            # Set Y range
                            plot_item.setYRange(min_db, 0)
                            
                            # Set X scale type
                            if freq_scale == "Logarithmic":
                                plot_item.setLogMode(x=True, y=False)
                            else:
                                plot_item.setLogMode(x=False, y=False)
                    except Exception as e:
                        print(f"Error updating spectrum in panel: {str(e)}")
                        continue
                        
        except Exception as e:
            print(f"Error updating spectrum settings: {str(e)}")
