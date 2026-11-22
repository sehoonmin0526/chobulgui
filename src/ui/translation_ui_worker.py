from src.logger import Logger
from src.translator.translator import SRTTranslator
from src.srt.srt import SRT
from PyQt6.QtCore import QThread, pyqtSignal
import asyncio

class TranslationUiWorker(QThread):
    translation_done = pyqtSignal() 
    progress_update = pyqtSignal(int)

    def __init__(self, text, translator: SRTTranslator):
        super().__init__()
        self.text = text
        self.translator = translator
        self.translator.set_progress_signal(self.progress_update)

    def run(self):
        try: 
            asyncio.run(self.translator.process_srt_async(self.text))
            self.translation_done.emit()
        except Exception as e: 
            Logger.error(f"번역 작업 실패. 오류 : {e}")