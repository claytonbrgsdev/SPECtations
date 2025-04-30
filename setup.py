from setuptools import setup

APP = ['src/gui.py']
DATA_FILES = []
OPTIONS = {
    'argv_emulation': True,
    'packages': ['numpy', 'scipy', 'sounddevice', 'PyQt6'],
    'resources': ['presets']
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
    name='SPECtations',
    version='1.0.0',
    description='Audio Spectrogram Analyzer'
)
