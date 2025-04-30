import sys
import PySide6.QtWidgets as QtWidgets

class TestWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test App")
        self.setGeometry(100, 100, 800, 600)
        
        label = QtWidgets.QLabel("Hello World!")
        self.setCentralWidget(label)

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec())
