import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from dashboard import SecureAccessDashboard


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Inter", 10))

    window = SecureAccessDashboard()
    window.show()

    sys.exit(app.exec())
