#!/bin/bash

# Clean previous build
rm -rf build dist SPECtations.spec

# Create the application bundle
pyinstaller --windowed --name SPECtations --add-data "presets:presets" src/gui.py

# Move the app to Applications folder
echo "Moving application to Applications folder..."
cp -r dist/SPECtations.app /Applications/

echo "Application has been installed to /Applications/SPECtations.app"
echo "You can now double-click the SPECtations icon in your Applications folder to run the program."
