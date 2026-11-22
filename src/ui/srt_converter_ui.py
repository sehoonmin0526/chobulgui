import os
from src.logger import Logger
from src.ui.translation_ui_worker import TranslationUiWorker
from src.ui.model_list_worker import ModelListWorker
from src.translator.translator import SRTTranslator, DEFAULT_MODEL
from src.srt.srt import SRT
from src.srt.srt_node import SRTNode
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QInputDialog,
    QFileDialog, QTextEdit, QProgressBar, QLabel, QCheckBox, QGroupBox, QGridLayout
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
import logging

class SRTConverterUI(QMainWindow):
    def __init__(self):
        super().__init__()

        self.system_msg_default = "다음 한국어 자막을 인도네시아어로 번역해줘. 문장이 이미 인도네시아어면 바꾸지 말고 그대로 응답 돌려줘"
        self.system_msg_file = "system_msg.txt"  # 시스템 메시지를 저장할 파일 경로
        self.system_msg = self.loadSystemMsg()  # 파일에서 메시지를 로드하거나 기본값으로 설정
        self.is_expanded = False  # 펼치기 상태를 저장
        self.is_translating = False

        self.last_model_file = "last_model.txt"  # 마지막 선택 모델을 저장할 파일 경로
        self.last_model = self.loadLastModel()  # 파일에서 로드하거나 기본값으로 설정

        self.initUI()
    
    def initUI(self):
        self.setWindowTitle("SRT 변환기")
        self.setGeometry(100, 100, 800, 600)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 전체 레이아웃
        main_layout = QVBoxLayout()

        # 파일 선택 UI (1개만 가능)
        self.file_label = QLabel("선택된 파일: 없음")
        self.file_select_btn = QPushButton("파일 선택")
        self.file_select_btn.clicked.connect(self.openFileDialog)
        
        self.file_remove_btn = QPushButton("파일 제거")
        self.file_remove_btn.clicked.connect(self.removeFile)

        self.start_conversion_btn = QPushButton("번역 시작")
        self.start_conversion_btn.setEnabled(False)
        self.start_conversion_btn.clicked.connect(self.startTranslation)

        # 모델 선택 UI (한 줄: 모델: xxx [선택])
        self.available_models = []
        self.model_label = QLabel(self.last_model)
        self.model_select_btn = QPushButton("선택")
        self.model_select_btn.setEnabled(False)  # 목록 조회가 끝나면 활성화
        self.model_select_btn.clicked.connect(self.openModelDialog)

        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("모델:"))
        model_layout.addWidget(self.model_label, stretch=1)
        model_layout.addWidget(self.model_select_btn)

        # 위쪽: [SRT 파일] [번역] 두 묶음을 나란히
        file_group = QGroupBox("SRT 파일")
        file_buttons_layout = QHBoxLayout()
        file_buttons_layout.addWidget(self.file_select_btn)
        file_buttons_layout.addWidget(self.file_remove_btn)
        file_group_layout = QVBoxLayout(file_group)
        file_group_layout.addWidget(self.file_label)
        file_group_layout.addLayout(file_buttons_layout)

        translate_group = QGroupBox("번역")
        translate_group_layout = QVBoxLayout(translate_group)
        translate_group_layout.addLayout(model_layout)
        translate_group_layout.addWidget(self.start_conversion_btn)

        top_layout = QHBoxLayout()
        top_layout.addWidget(file_group, stretch=1)
        top_layout.addWidget(translate_group, stretch=1)

        # 진행 상황 바 (텍스트 창 바로 위 한 줄)
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(
            "QProgressBar { height: 20px; border-radius: 5px; border: 1px solid gray; text-align: center; font-weight: bold; } QProgressBar::chunk { background-color: #4CAF50; border-radius: 5px; }")
        self.progress_bar.setValue(0)
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.save_btn = QPushButton("저장")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.saveFile)
        
        self.merge_checkbox = QCheckBox("기존 자막과 합치기")
        self.merge_checkbox.setToolTip("번역 아래 줄에 원문 자막을 함께 표시하고, 저장할 때도 그대로 저장합니다")
        self.merge_checkbox.setEnabled(False)  # 번역이 끝나면 활성화
        self.merge_checkbox.toggled.connect(lambda: self.showTranslation())

        progress_layout = QHBoxLayout()
        progress_layout.addWidget(QLabel("진행 상황"))
        progress_layout.addWidget(self.progress_bar, stretch=1)

        # 하단: 원본 및 번역 결과 텍스트 창 (번역 결과 쪽 머리줄에 합치기/저장)
        self.original_text = QTextEdit()
        self.original_text.setReadOnly(True)
        self.original_text.setPlaceholderText("원본 SRT 내용")

        self.converted_text = QTextEdit()
        self.converted_text.setReadOnly(True)
        self.converted_text.setPlaceholderText("변환된 파일 내용")

        result_header_layout = QHBoxLayout()
        result_header_layout.addWidget(QLabel("번역 결과"))
        result_header_layout.addStretch()
        result_header_layout.addWidget(self.merge_checkbox)
        result_header_layout.addWidget(self.save_btn)

        # 두 창의 머리줄 높이가 달라도 텍스트 창 위치가 맞도록 격자로 배치
        text_area_layout = QGridLayout()
        text_area_layout.addWidget(QLabel("원본"), 0, 0)
        text_area_layout.addLayout(result_header_layout, 0, 1)
        text_area_layout.addWidget(self.original_text, 1, 0)
        text_area_layout.addWidget(self.converted_text, 1, 1)

        # 시스템 메시지 UI
        self.system_msg_editor = QTextEdit()
        self.system_msg_editor.setPlainText(self.system_msg)
        self.system_msg_editor.setReadOnly(True)  # 초기에는 읽기 전용
        self.system_msg_editor.setMaximumHeight(50)  # 접힌 상태에서 높이 제한

        self.expand_btn = QPushButton("프롬프트 수정")
        self.expand_btn.clicked.connect(self.toggleExpand)

        self.reset_btn = QPushButton("프롬프트 초기화")
        self.reset_btn.clicked.connect(self.resetSystemMsg)

        # 버튼 레이아웃
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.expand_btn)
        button_layout.addWidget(self.reset_btn)

        # 시스템 메시지 레이아웃
        system_msg_layout = QVBoxLayout()
        system_msg_layout.addWidget(self.system_msg_editor)
        system_msg_layout.addLayout(button_layout)

        # 로그 창
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(100)
        
        main_layout.addLayout(system_msg_layout)
        main_layout.addLayout(top_layout)
        main_layout.addLayout(progress_layout)
        main_layout.addLayout(text_area_layout)
        main_layout.addWidget(QLabel("로그"))
        main_layout.addWidget(self.log_text)

        central_widget.setLayout(main_layout)

        # 로거 설정
        handler = QTextEditLogger(self.log_text)
        Logger.setUITextEdit(handler)

        # 모델 목록 비동기 조회
        self.refreshModelList()

    def refreshModelList(self):
        Logger.info("모델 목록 조회 중...")
        self.model_list_worker = ModelListWorker()
        self.model_list_worker.models_loaded.connect(self.onModelsLoaded)
        self.model_list_worker.start()

    def onModelsLoaded(self, models):
        if not models:
            Logger.warning(f"모델 목록을 가져오지 못했습니다. {self.last_model} 모델을 사용합니다.")
            return

        self.available_models = models
        self.model_select_btn.setEnabled(not self.is_translating)

        if self.last_model not in models and DEFAULT_MODEL in models:
            Logger.warning(f"{self.last_model} 모델을 사용할 수 없어 {DEFAULT_MODEL}(으)로 변경합니다.")
            self.setModel(DEFAULT_MODEL)

        Logger.info(f"모델 목록 조회 완료 ({len(models)}개)")

    def openModelDialog(self):
        current_index = (
            self.available_models.index(self.last_model) if self.last_model in self.available_models else 0
        )
        model, ok = QInputDialog.getItem(
            self, "모델 선택", "모델 (최신순):", self.available_models, current_index, False
        )
        if ok and model:
            self.setModel(model)

    def setModel(self, model: str):
        self.last_model = model
        self.model_label.setText(model)
        self.saveLastModel(model)

    def loadLastModel(self):
        """파일에서 마지막 선택 모델을 로드"""
        if os.path.exists(self.last_model_file):
            with open(self.last_model_file, "r", encoding="utf-8") as file:
                content = file.read().strip()
                if content:
                    return content
        return DEFAULT_MODEL

    def saveLastModel(self, model: str):
        """현재 선택된 모델을 파일에 저장"""
        with open(self.last_model_file, "w", encoding="utf-8") as file:
            file.write(model)

    def toggleExpand(self):
        """프롬프트 수정 버튼 클릭 시 호출"""
        self.is_expanded = not self.is_expanded
        if self.is_expanded:
            self.system_msg_editor.setReadOnly(False)  # 수정 가능
            self.system_msg_editor.setMaximumHeight(200)  # 높이 확장
            self.expand_btn.setText("수정 완료")
        else:
            self.system_msg_editor.setReadOnly(True)  # 읽기 전용
            self.system_msg_editor.setMaximumHeight(50)  # 높이 제한
            self.expand_btn.setText("프롬프트 수정")
            # 수정된 메시지 저장
            self.system_msg = self.system_msg_editor.toPlainText().strip()
            self.saveSystemMsg()  # 수정된 메시지를 파일에 저장
            Logger.info(f"시스템 메시지 수정됨: {self.system_msg}")

    def resetSystemMsg(self):
        """디폴트 메시지로 복원"""
        self.system_msg = self.system_msg_default
        self.system_msg_editor.setPlainText(self.system_msg)
        self.saveSystemMsg()  # 디폴트 메시지를 파일에 저장
        Logger.info("시스템 메시지가 기본값으로 복원되었습니다.")

    def loadSystemMsg(self):
        """파일에서 시스템 메시지를 로드"""
        if os.path.exists(self.system_msg_file):
            with open(self.system_msg_file, "r", encoding="utf-8") as file:
                content = file.read().strip()
                if content:
                    Logger.info("시스템 메시지가 파일에서 로드되었습니다.")
                    return content
        Logger.info("시스템 메시지가 기본값으로 설정되었습니다.")
        return self.system_msg_default

    def saveSystemMsg(self):
        """현재 시스템 메시지를 파일에 저장"""
        with open(self.system_msg_file, "w", encoding="utf-8") as file:
            file.write(self.system_msg)
        Logger.info("시스템 메시지가 파일에 저장되었습니다.")

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
    
    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if file_path.lower().endswith(".srt"):
                self.file_label.setText(f"선택된 파일: {file_path}")
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.original_text.setPlainText(f.read())
                Logger.info(f"파일 추가됨: {file_path}")
                self.start_conversion_btn.setEnabled(True)
            else:
                Logger.warning("잘못된 파일 형식입니다. SRT 파일만 지원됩니다.")
    
    
    def openFileDialog(self):
        file, _ = QFileDialog.getOpenFileName(self, "SRT 파일 선택", "", "SRT Files (*.srt)")
        if file:
            self.file_label.setText(f"선택된 파일: {file}")
            with open(file, 'r', encoding='utf-8') as f:
                self.original_text.setPlainText(f.read())
            self.start_conversion_btn.setEnabled(True)
            Logger.info(f"파일 추가됨: {file}")
    
    def removeFile(self):
        self.file_label.setText("선택된 파일: 없음")
        self.original_text.clear()
        self.converted_text.clear()
        self.start_conversion_btn.setEnabled(False)
        self.merge_checkbox.setEnabled(False)
        self.save_btn.setEnabled(False)
        Logger.info("파일 선택 취소됨")

    def setTranslating(self, translating: bool):
        self.is_translating = translating
        enabled = not translating
        for widget in (
            self.file_select_btn, self.file_remove_btn, self.start_conversion_btn,
            self.expand_btn, self.reset_btn, self.system_msg_editor,
        ):
            widget.setEnabled(enabled)
        self.model_select_btn.setEnabled(enabled and bool(self.available_models))
        if translating:
            self.save_btn.setEnabled(False)
            self.merge_checkbox.setEnabled(False)

    def startTranslation(self):
        text = self.original_text.toPlainText()
        if not text.strip():
            Logger.warning("변환할 내용이 없습니다.")
            return

        Logger.info("번역 시작")
        self.setTranslating(True)
        self.progress_bar.setValue(0)

        Logger.info(f"선택된 모델: {self.last_model}")
        self.translator = SRTTranslator(system_msg=self.system_msg, model=self.last_model)

        # 백그라운드 작업 실행
        self.worker = TranslationUiWorker(text, self.translator)
        self.worker.translation_done.connect(self.onTranslationDone)
        self.worker.progress_update.connect(self.updateProgress)
        self.worker.finished.connect(lambda: self.setTranslating(False))
        self.worker.start()

    def updateProgress(self, value):
        self.progress_bar.setValue(value)

    def onTranslationDone(self):
        self.showTranslation()
        Logger.info("!! 번역 완료 !!")
        self.save_btn.setEnabled(True)
        self.merge_checkbox.setEnabled(True)

    def buildOutputSrt(self) -> SRT:
        """체크 여부에 따라 번역만, 또는 번역 아래 줄에 원문을 붙인 SRT를 만듦"""
        srt = self.translator.srt
        if not self.merge_checkbox.isChecked():
            return srt

        merged = SRT()
        for node, original in zip(srt.get_nodes(), self.translator.original_texts):
            # 원문을 그대로 둔 줄(이미 인도네시아어였던 줄 등)은 같은 문장이 두 번 나오지 않게 한 번만
            text = node.text if node.text.strip() == original.strip() else f"{node.text}\n{original}"
            merged.append_node(SRTNode(node.number, node.timestamp, text))
        return merged

    def showTranslation(self):
        self.converted_text.setPlainText(self.buildOutputSrt().get_all_text())
    
    def saveFile(self):
        if self.translator is None:
            Logger.error("Translator is null!!")
            return
        
        # 저장 경로 선택 다이얼로그
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "파일 저장",
            "output.srt",           # 기본 파일명
            "SRT Files (*.srt);;Text Files (*.txt)"  # 파일 필터
        )

        if file_path:
            self.buildOutputSrt().save(file_path)
            Logger.info(f"파일 저장 완료: {file_path}")
        else:
            Logger.info("파일 저장 취소됨")
            

class _LogSignal(QObject):
    message = pyqtSignal(str)


class QTextEditLogger(logging.Handler):
    # 워커 스레드에서 로그가 와도 위젯 갱신은 시그널을 통해 메인(UI) 스레드에서만 하도록 함
    def __init__(self, text_widget):
        super().__init__()
        self.widget = text_widget
        self.signal = _LogSignal()
        self.signal.message.connect(self._append)

    def emit(self, record):
        self.signal.message.emit(self.format(record))

    def _append(self, msg):
        self.widget.append(msg)
        self.widget.ensureCursorVisible()
