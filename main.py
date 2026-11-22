from PyQt6.QtWidgets import QApplication 
from src.ui.srt_converter_ui import SRTConverterUI
import sys
import faulthandler

if __name__ == "__main__":
    # segfault 등으로 프로세스가 죽을 때 모든 스레드의 파이썬 콜스택을 stderr에 출력
    faulthandler.enable()
    app = QApplication(sys.argv)
    window = SRTConverterUI()
    window.show()
    sys.exit(app.exec())
