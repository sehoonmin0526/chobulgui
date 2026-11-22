import asyncio
from PyQt6.QtCore import QThread, pyqtSignal

from src.translator.translator import SRTTranslator
from src.logger import Logger


class ModelListWorker(QThread):
    models_loaded = pyqtSignal(list)

    def run(self):
        try:
            models = asyncio.run(SRTTranslator.fetch_available_models())
            self.models_loaded.emit(models)
        except Exception as e:
            Logger.error(f"모델 목록 조회 실패: {e}")
            self.models_loaded.emit([])
