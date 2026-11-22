# Segmentation fault 원인 분석 보고서

## 요약

번역이 끝난 직후 macOS에서 앱이 `zsh: segmentation fault`로 종료되는 문제가 있었다.
원인은 **번역 워커 스레드(QThread)에서 로그를 남길 때, 로그 핸들러가 UI 위젯(QTextEdit)을 직접 갱신한 것**이다.
Qt 위젯은 메인(UI) 스레드에서만 다뤄야 하는데, 다른 스레드에서 건드리면 메인 스레드의 화면 갱신과 겹치는 순간 메모리 손상으로 프로세스가 죽는다.

로그 핸들러가 Qt 시그널을 통해 메인 스레드에서 위젯을 갱신하도록 수정했다. 크래시가 다시 나면 원인을 바로 찾을 수 있게 `faulthandler`도 켜두었다.

> 수정 후 macOS 실기기에서 재현 테스트는 아직 하지 않았다.

## 증상

- 발생일: 2026-11-08, macOS (`requirements.txt` 기준 PyQt6 6.8.1)
- 번역 요청 → 응답 수신 → 통계 로그 출력 직후 프로세스 종료
- 2회 실행해 2회 모두 같은 지점에서 종료됨 (모델 `gpt-6.1-terra`, `gpt-6.1-sol`)
- 파이썬 Traceback 없이 셸 메시지만 출력됨

```
2026-11-08 11:19:04,961 - INFO - ⏱ 소요 시간: 총 62.6초 (첫 출력까지 3.1초 + 출력 59.5초)
2026-11-08 11:19:04,971 - INFO - 🔢 토큰 [gpt-6.1-sol]: 입력 7,836 (캐시 0) / 출력 6,766 = 생각 22 (0%) + 번역문 6,744
zsh: segmentation fault  python3 main.py
```

정상이라면 이어서 출력돼야 할 `!! 번역 완료 !!` 로그가 나오지 않았다.

## 원인

### 문제 코드

`src/ui/srt_converter_ui.py`의 로그 핸들러가 로그를 받으면 즉시 위젯을 갱신했다.

```python
class QTextEditLogger(logging.Handler):
    def emit(self, record):
        msg = self.format(record)
        self.widget.append(msg)          # 호출한 스레드에서 그대로 위젯 조작
        self.widget.ensureCursorVisible()
```

`logging` 핸들러의 `emit()`은 **로그를 남긴 스레드에서** 실행된다.
번역은 `TranslationUiWorker`(QThread)에서 돌아가므로, 워커 스레드에서 남긴 로그는 워커 스레드가 `QTextEdit`을 직접 수정하게 된다.

### 원인으로 판단한 근거

1. 워커 스레드 안에서 남기는 로그는 `SRTTranslator._log_stats()`의 `⏱ 소요 시간`, `🔢 토큰` 두 줄뿐이다(오류가 없을 때 기준). 크래시는 정확히 이 두 줄 직후에 났다.
2. 로거에는 콘솔 핸들러(`StreamHandler`)가 먼저, UI 핸들러가 나중에 붙어 있다. 그래서 `🔢 토큰` 줄이 콘솔에 찍힌 뒤 UI 핸들러가 위젯을 건드리는 순간 죽은 흐름과 맞는다.
3. 메인 스레드에서 실행되는 `onTranslationDone()`의 `!! 번역 완료 !!` 로그는 나오지 않았다.
4. 다른 로그(`모델 목록 조회 완료` 등)는 모두 메인 스레드의 슬롯에서 남기므로 문제가 없었다.

## 간헐적으로 발생하는 이유

다른 스레드에서 위젯을 건드린다고 매번 죽지는 않는다. **두 스레드가 같은 순간에 같은 내부 데이터를 다룰 때만** 죽는다.

- 메인 스레드는 이벤트 루프에서 글자 배치, 스크롤바, 다시 그리기 등을 위해 `QTextEdit` 내부 데이터를 계속 읽고 쓴다.
- 워커 스레드의 `append()`가 메인 스레드가 쉬는 사이에 끝나면 아무 일도 없다.
- 메인 스레드가 그리는 도중에 겹치면, 이미 지워졌거나 반쯤 바뀐 데이터를 읽어 segfault가 난다.

겹치느냐 마느냐는 그때그때의 스레드 실행 순서에 달려 있다. 같은 실행 안에서도 `⏱ 소요 시간` 줄은 무사히 지나가고 다음 줄에서 죽었다.

이번 경우에 크래시가 잘 난 요인으로 아래를 꼽을 수 있다.

- 번역 중 진행률 시그널이 계속 들어와 메인 스레드가 진행 바를 자주 다시 그리고 있었다.
- 워커 스레드가 로그 두 줄을 연달아 위젯에 썼다.
- 로그가 길고 이모지가 들어 있어 글자 배치 계산이 오래 걸렸고, 그만큼 겹칠 시간도 길었다.
- macOS(Cocoa)는 스레드 규칙 위반에 상대적으로 민감해, Windows에서는 잘 드러나지 않던 문제가 macOS에서 드러난 것으로 보인다.

## 콜스택이 출력되지 않은 이유

- 파이썬 Traceback은 **파이썬 예외**가 났을 때 인터프리터가 직접 출력한다.
- 이번 크래시는 Qt C++ 코드가 잘못된 메모리에 접근해 OS가 프로세스를 즉시 종료(SIGSEGV)한 경우라서 파이썬이 아무것도 출력할 기회가 없었다.
- `zsh: segmentation fault`는 파이썬이 아니라 셸이 출력한 메시지다.

## 조치 내용

### 1. 로그 핸들러의 위젯 갱신을 메인 스레드로 보냄 (`src/ui/srt_converter_ui.py`)

```diff
-from PyQt6.QtCore import Qt
+from PyQt6.QtCore import Qt, QObject, pyqtSignal
@@
-class QTextEditLogger(logging.Handler):
-    def __init__(self, text_widget):
-        super().__init__()
-        self.widget = text_widget
-
-    def emit(self, record):
-        msg = self.format(record)
-        self.widget.append(msg)
-        self.widget.ensureCursorVisible()
+class _LogSignal(QObject):
+    message = pyqtSignal(str)
+
+
+class QTextEditLogger(logging.Handler):
+    # 워커 스레드에서 로그가 와도 위젯 갱신은 시그널을 통해 메인(UI) 스레드에서만 하도록 함
+    def __init__(self, text_widget):
+        super().__init__()
+        self.widget = text_widget
+        self.signal = _LogSignal()
+        self.signal.message.connect(self._append)
+
+    def emit(self, record):
+        self.signal.message.emit(self.format(record))
+
+    def _append(self, msg):
+        self.widget.append(msg)
+        self.widget.ensureCursorVisible()
```

`_LogSignal`은 메인 스레드에서 생성된다. 워커 스레드에서 `emit`하면 Qt가 자동으로 큐 연결(QueuedConnection)을 사용해, `_append`가 메인 스레드의 이벤트 루프에서 실행된다.

### 2. 크래시 시 파이썬 콜스택 출력 (`main.py`)

```diff
 import sys
+import faulthandler

 if __name__ == "__main__":
+    # segfault 등으로 프로세스가 죽을 때 모든 스레드의 파이썬 콜스택을 stderr에 출력
+    faulthandler.enable()
     app = QApplication(sys.argv)
```

이제 segfault가 나면 `Fatal Python error: Segmentation fault`와 함께 스레드별 파이썬 콜스택(파일, 줄 번호)이 출력된다.
단, Qt C++ 내부 스택은 보이지 않는다. 그 부분은 macOS 크래시 리포트(`~/Library/Logs/DiagnosticReports/Python-*.ips` 또는 Console.app → 크래시 리포트)에서 확인할 수 있다.

## 남은 확인 사항

- [ ] macOS에서 같은 SRT 파일로 여러 번 번역해 크래시가 다시 나지 않는지 확인
- [ ] 2026-11-08 크래시의 `.ips` 리포트가 남아 있다면 열어서, 죽은 스레드가 워커 스레드의 `QTextEdit` 관련 호출인지 확인

## 재발 방지 원칙

- Qt 위젯은 메인 스레드에서만 조작한다. 워커 스레드에서는 시그널만 내보낸다.
- 워커 스레드에서 실행되는 코드(`SRTTranslator` 등)가 UI에 영향을 주는 경로를 새로 만들 때는 시그널을 거치는지 확인한다.
