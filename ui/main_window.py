# ui/main_window.py
import os
import sounddevice as sd
import soundfile as sf
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QTextEdit, QComboBox, QLabel, 
                             QGroupBox, QRadioButton, QStackedWidget, QSlider,
                             QFileDialog, QLineEdit, QCheckBox, QButtonGroup)
from PyQt6.QtCore import Qt

from config import SAMPLE_RATE, TEMP_RECORD_FILE, DEFAULT_PROMPT
from ui.styles import STYLE_BTN_DEFAULT_REF, STYLE_BTN_RECORDING_REF, STYLE_BTN_DEFAULT_TRANS, STYLE_BTN_RECORDING_TRANS
from workers.ai_processor import AIProcessingWorker
from workers.audio_player import AudioPlayWorker


class MainWindow(QWidget):
    def __init__(self, ai_engine):
        super().__init__()
        self.ai_engine = ai_engine
        from core import AudioCapture
        self.audio_capture = AudioCapture(SAMPLE_RATE)
        
        self.worker = None
        self.play_worker = None
        self.current_tts_wav = None 
        self._current_recording_is_cloning = None
        
        self.langs_dict = self.ai_engine.get_supported_languages()
        self.sorted_lang_names = sorted([k.title() for k in self.langs_dict.keys()])
        
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("VoxCPM2 음성 생성")
        self.resize(600, 800)
        main_layout = QVBoxLayout()
        
        # [1] 오디오 장치 설정
        dev_group = QGroupBox("🎙️ 오디오 설정")
        dev_layout = QVBoxLayout()
        dev_layout.addWidget(QLabel("오디오 송출 장치 (가상 오디오 케이블):"))
        self.device_combo = QComboBox()
        devices = sd.query_devices()
        output_devices = [dev['name'] for dev in devices if dev['max_output_channels'] > 0]
        self.device_combo.addItems(["장치 선택 필요"] + output_devices)
        dev_layout.addWidget(self.device_combo)
        dev_group.setLayout(dev_layout)

        # [2] 목소리 프로필 설정
        voice_group = QGroupBox("👤 목소리 프로필 설정")
        voice_layout = QVBoxLayout()
        
        # 프롬프트(디자인)와 레퍼런스(클로닝)를 동시에 사용할 수 있도록 체크박스로 전환
        self.mode_design = QCheckBox("보이스 디자인 (프롬프트)")
        self.mode_clone = QCheckBox("보이스 클로닝 (레퍼런스 파일)")
        self.mode_design.setChecked(True)

        mode_layout = QHBoxLayout()
        mode_layout.addWidget(self.mode_design)
        mode_layout.addWidget(self.mode_clone)
        voice_layout.addLayout(mode_layout)
        
        voice_layout.addWidget(QLabel("보이스 프롬프트 (영문 입력):"))
        # 프롬프트는 단일라인 입력으로 간결하게 변경
        self.prompt_input = QLineEdit(DEFAULT_PROMPT)
        self.prompt_input.setMaximumHeight(30)
        voice_layout.addWidget(self.prompt_input)
        
        ref_file_layout = QHBoxLayout()
        self.ref_path_input = QLineEdit()
        self.ref_path_input.setPlaceholderText("오디오 파일 선택 또는 아래 버튼으로 녹음")
        self.ref_path_input.setReadOnly(True)
        
        btn_browse = QPushButton("찾아보기 📁")
        btn_browse.clicked.connect(self.browse_ref_file)
        ref_file_layout.addWidget(self.ref_path_input)
        ref_file_layout.addWidget(btn_browse)
        voice_layout.addLayout(ref_file_layout)
        
        self.btn_record_ref = QPushButton("🎙️ 클릭해서 내 목소리 샘플 녹음 시작 (3~5초 권장)")
        self.btn_record_ref.setStyleSheet(STYLE_BTN_DEFAULT_REF)
        self.btn_record_ref.clicked.connect(lambda: self.toggle_recording(is_cloning=True))
        voice_layout.addWidget(self.btn_record_ref)
        
        cfg_container = QHBoxLayout()
        self.cfg_slider = QSlider(Qt.Orientation.Horizontal)
        self.cfg_slider.setRange(10, 70)
        self.cfg_slider.setValue(30)
        self.cfg_val_label = QLabel("현재 값: 3.0")
        self.cfg_slider.valueChanged.connect(lambda v: self.cfg_val_label.setText(f"현재 값: {v/10.0}"))
        cfg_container.addWidget(QLabel("CFG Scale:"))
        cfg_container.addWidget(self.cfg_slider)
        cfg_container.addWidget(self.cfg_val_label)
        voice_layout.addLayout(cfg_container)
        
        steps_container = QHBoxLayout()
        self.steps_slider = QSlider(Qt.Orientation.Horizontal)
        self.steps_slider.setRange(5, 30)
        self.steps_slider.setValue(7)
        self.steps_val_label = QLabel("현재 값: 7")
        self.steps_slider.valueChanged.connect(lambda v: self.steps_val_label.setText(f"현재 값: {v}"))
        steps_container.addWidget(QLabel("Timesteps:"))
        steps_container.addWidget(self.steps_slider)
        steps_container.addWidget(self.steps_val_label)
        voice_layout.addLayout(steps_container)
        
        voice_group.setLayout(voice_layout)

        # 상단에 오디오 설정과 프로필을 가로로 배치해 화면을 깔끔하게 정리
        top_layout = QHBoxLayout()
        top_layout.addWidget(dev_group, 1)
        top_layout.addWidget(voice_group, 2)
        main_layout.addLayout(top_layout)
        
        # [3] 작동 모드 및 스택 위젯
        mode_select_layout = QHBoxLayout()
        # 번역 모드와 TTS 모드는 항상 상호 배타적이도록 버튼 그룹에 넣음
        self.radio_text_mode = QRadioButton("일반 텍스트 입력 TTS 송출")
        self.radio_trans_mode = QRadioButton("음성 입력 번역 송출")
        self.radio_text_mode.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.setExclusive(True)
        mode_group.addButton(self.radio_text_mode)
        mode_group.addButton(self.radio_trans_mode)
        mode_select_layout.addWidget(self.radio_text_mode)
        mode_select_layout.addWidget(self.radio_trans_mode)
        main_layout.addLayout(mode_select_layout)
        
        self.mode_stacked = QStackedWidget()
        
        # 모드 A 화면: 텍스트 TTS
        page_text = QWidget()
        layout_text = QVBoxLayout(page_text)
        self.text_tts_input = QTextEdit()
        self.text_tts_input.setMaximumHeight(65)
        layout_text.addWidget(QLabel("보낼 대사 타이핑 입력:"))
        layout_text.addWidget(self.text_tts_input)
        
        self.radio_tx_imm_txt = QRadioButton("생성 즉시 출력")
        self.radio_tx_man_txt = QRadioButton("확인 후 수동 출력")
        self.radio_tx_imm_txt.setChecked(True)
        tx_layout = QHBoxLayout()
        tx_layout.addWidget(self.radio_tx_imm_txt)
        tx_layout.addWidget(self.radio_tx_man_txt)
        layout_text.addLayout(tx_layout)
        
        btn_send_txt = QPushButton("⚡ AI 음성 생성 시작")
        btn_send_txt.setStyleSheet("background-color: #008CBA; color: white; height: 38px;")
        btn_send_txt.clicked.connect(self.process_text_tts)
        btn_manual_txt = QPushButton("🎙️ 수동 송출")
        btn_manual_txt.clicked.connect(self.trigger_manual_audio_play)
        btns_txt = QHBoxLayout()
        btns_txt.addWidget(btn_send_txt)
        btns_txt.addWidget(btn_manual_txt)
        layout_text.addLayout(btns_txt)
        
        # 모드 B 화면: 음성 번역
        page_trans = QWidget()
        layout_trans = QVBoxLayout(page_trans)
        
        lang_layout = QHBoxLayout()
        self.src_lang = QComboBox()
        self.tgt_lang = QComboBox()
        self.src_lang.addItems(self.sorted_lang_names)
        self.tgt_lang.addItems(self.sorted_lang_names)
        if "Korean" in self.sorted_lang_names: self.src_lang.setCurrentText("Korean")
        if "English" in self.sorted_lang_names: self.tgt_lang.setCurrentText("English")
        lang_layout.addWidget(self.src_lang)
        lang_layout.addWidget(QLabel("→"))
        lang_layout.addWidget(self.tgt_lang)
        layout_trans.addLayout(lang_layout)
        
        # 참고: 분할(separator) 기능 제거 — 텍스트 전체를 한 번에 번역합니다.
        
        self.radio_tx_imm_trans = QRadioButton("번역 즉시 출력")
        self.radio_tx_man_trans = QRadioButton("확인 후 수동 출력")
        self.radio_tx_imm_trans.setChecked(True)
        tx_layout_trans = QHBoxLayout()
        tx_layout_trans.addWidget(self.radio_tx_imm_trans)
        tx_layout_trans.addWidget(self.radio_tx_man_trans)
        layout_trans.addLayout(tx_layout_trans)
        
        self.ptt_btn = QPushButton("🔴 클릭해서 녹음 시작 (다시 클릭 시 종료)")
        self.ptt_btn.setStyleSheet(STYLE_BTN_DEFAULT_TRANS)
        self.ptt_btn.clicked.connect(lambda: self.toggle_recording(is_cloning=False))
        btn_manual_trans = QPushButton("🎙️ 수동 송출")
        btn_manual_trans.clicked.connect(self.trigger_manual_audio_play)
        btns_trans = QHBoxLayout()
        btns_trans.addWidget(self.ptt_btn)
        btns_trans.addWidget(btn_manual_trans)
        layout_trans.addLayout(btns_trans)
        
        self.mode_stacked.addWidget(page_text)
        self.mode_stacked.addWidget(page_trans)
        main_layout.addWidget(self.mode_stacked)
        
        self.radio_text_mode.toggled.connect(lambda checked: checked and self.mode_stacked.setCurrentIndex(0))
        self.radio_trans_mode.toggled.connect(lambda checked: checked and self.mode_stacked.setCurrentIndex(1))

        # [4] 제어 버튼 및 로그 창
        btn_cancel = QPushButton("🛑 작업 취소 / 송출 중단")
        btn_cancel.setStyleSheet("background-color: #FF5722; color: white; height: 40px;")
        btn_cancel.clicked.connect(self.interrupt_task)
        main_layout.addWidget(btn_cancel)

        self.status_box = QTextEdit()
        self.status_box.setReadOnly(True)
        main_layout.addWidget(self.status_box)
        self.setLayout(main_layout)

    # --- 통합 오디오 캡처 컨트롤러 ---
    def _append_log(self, text):
        """로그 텍스트를 status_box에 누적 (히스토리 유지)"""
        self.status_box.append(text)

    def toggle_recording(self, is_cloning):
        if self.worker and self.worker.isRunning():
            self.status_box.append("⚠️ 시스템이 연산 작업 중입니다. 대기해 주세요.")
            return

        if self.audio_capture.is_recording:
            audio_data = self.audio_capture.stop()
            self._update_record_ui(is_cloning, is_recording=False)
            self._process_recorded_audio(audio_data, is_cloning)
            self._current_recording_is_cloning = None
        else:
            try:
                self.audio_capture.start()
                self._current_recording_is_cloning = is_cloning
                self._update_record_ui(is_cloning, is_recording=True)
            except Exception as e:
                self._current_recording_is_cloning = None
                self._update_record_ui(is_cloning, is_recording=False)
                self.status_box.append(f"❌ 마이크 초기화 실패: {str(e)}")

    def _update_record_ui(self, is_cloning, is_recording):
        btn = self.btn_record_ref if is_cloning else self.ptt_btn
        if is_recording:
            btn.setText("🎤 녹음 진행 중... 완료하려면 다시 클릭하세요")
            btn.setStyleSheet(STYLE_BTN_RECORDING_REF if is_cloning else STYLE_BTN_RECORDING_TRANS)
            self.status_box.append("🎙️ 클로닝 샘플 수집 중..." if is_cloning else "🎙️ 번역을 위한 음성 입력 중...")
        else:
            if is_cloning:
                btn.setText("🎙️ 클릭해서 내 목소리 샘플 녹음 시작 (3~5초 권장)")
                btn.setStyleSheet(STYLE_BTN_DEFAULT_REF)
            else:
                btn.setText("🔴 클릭해서 녹음 시작 (다시 클릭 시 종료)")
                btn.setStyleSheet(STYLE_BTN_DEFAULT_TRANS)

    def _process_recorded_audio(self, audio_data, is_cloning):
        if audio_data is None or len(audio_data) == 0:
            self.status_box.append("⚠️ 녹음된 데이터가 없습니다.")
            return

        if is_cloning:
            sf.write(TEMP_RECORD_FILE, audio_data, SAMPLE_RATE)
            abs_path = os.path.abspath(TEMP_RECORD_FILE)
            self.ref_path_input.setText(abs_path)
            self.status_box.append(f"✅ 클로닝 레퍼런스 임시 저장 완료:\n{abs_path}")
        else:
            self.start_worker("voice_translation", audio_data=audio_data)

    # --- 워커 매니저 및 유틸리티 ---
    def process_text_tts(self):
        if self.worker and self.worker.isRunning():
            self.status_box.append("⚠️ 시스템이 작업 중입니다.")
            return
        self.start_worker("text_tts", text_data=self.text_tts_input.toPlainText())

    def start_worker(self, task_type, audio_data=None, text_data=""):
        self.current_tts_wav = None 
        # 모드 결정: 디자인+클로닝 둘다 체크 시 하이브리드 모드
        if self.mode_design.isChecked() and self.mode_clone.isChecked():
            chosen_mode = "보이스 하이브리드"
        elif self.mode_clone.isChecked():
            chosen_mode = "보이스 클로닝"
        else:
            chosen_mode = "보이스 디자인"

        config = {
            'mode': chosen_mode,
            'prompt': self.prompt_input.text(),
            'ref_path': self.ref_path_input.text().strip(),
            'device': self.device_combo.currentText(),
            'cfg': self.cfg_slider.value() / 10.0,
            'steps': self.steps_slider.value(),
            'src_code': self.langs_dict.get(self.src_lang.currentText().lower(), "auto"),
            'tgt_code': self.langs_dict.get(self.tgt_lang.currentText().lower(), "en"),
            'tx_mode': "수동" if (self.radio_tx_man_txt.isChecked() if task_type == "text_tts" else self.radio_tx_man_trans.isChecked()) else "즉시"
        }
        
        # 클로닝 또는 하이브리드 모드 유효성 검사 (레퍼런스 파일 필요)
        if config['mode'] in ("보이스 클로닝", "보이스 하이브리드"):
            if not config['ref_path']:
                self.status_box.append("⚠️ 클로닝/하이브리드 모드: 레퍼런스 파일 경로가 비어있습니다.\n\"찾아보기\" 또는 \"녹음\"으로 파일을 선택해 주세요.")
                return
            if not os.path.exists(config['ref_path']):
                self.status_box.append(f"❌ 클로닝/하이브리드 모드: 지정된 파일을 찾을 수 없습니다.\n경로: {config['ref_path']}")
                return
        
        self.worker = AIProcessingWorker(task_type, audio_data, text_data, config, self.ai_engine)
        self.worker.log_signal.connect(self._append_log)  # 로그 누적 방식 사용
        self.worker.result_audio_signal.connect(self._on_tts_result_received)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def interrupt_task(self):
        sd.stop()
        self.current_tts_wav = None 
        if self.audio_capture.is_recording:
            audio_data = self.audio_capture.stop()
            self._update_record_ui(self._current_recording_is_cloning, is_recording=False)
            self._current_recording_is_cloning = None
            self.status_box.append("🛑 녹음이 중단되었습니다.")

        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.status_box.append("🛑 사용자에 의해 작업이 강제 취소되었습니다.")
        elif self.play_worker and self.play_worker.isRunning():
            self.play_worker.requestInterruption()
            self.status_box.append("🛑 수동 송출이 중단되었습니다.")
        else:
            self.status_box.append("ℹ️ 취소 완료. (진행 중인 작업 없음)")

    def _on_tts_result_received(self, wav):
        self.current_tts_wav = wav

    def _on_worker_finished(self):
        if self.worker:
            self.worker.deleteLater()
            self.worker = None

    def _on_play_finished(self):
        self.status_box.append("✅ 수동 송출 완수!")

    def _on_play_error(self, error_msg):
        self.status_box.append(f"❌ 송출 실패: {error_msg}")

    def _on_play_worker_finished(self):
        if self.play_worker:
            self.play_worker.deleteLater()
            self.play_worker = None

    def trigger_manual_audio_play(self):
        if self.current_tts_wav is None:
            self.status_box.append("⚠️ 마이크로 전송할 오디오가 준비되지 않았습니다.")
            return
            
        output_device = self.device_combo.currentText()
        if output_device == "장치 선택 안함 (미리듣기만)":
            self.status_box.append("⚠️ 송출 장치(가상 케이블)를 먼저 설정해 주세요.")
            return

        devices = sd.query_devices()
        dev_id = next((i for i, d in enumerate(devices) if d['name'] == output_device), None)
        
        if dev_id is not None:
            self.status_box.append("📢 [수동 제어] 오디오 송출 중...")
            self.play_worker = AudioPlayWorker(self.current_tts_wav, self.ai_engine.tts_sr, dev_id)
            self.play_worker.finished_signal.connect(self._on_play_finished)
            self.play_worker.error_signal.connect(self._on_play_error)
            self.play_worker.finished.connect(self._on_play_worker_finished)
            self.play_worker.start()
        else:
            self.status_box.append("❌ 지정된 오디오 디바이스를 찾을 수 없습니다.")

    def browse_ref_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "레퍼런스 파일 선택", "", "오디오 파일 (*.wav *.mp3 *.flac)")
        if file_path:
            self.ref_path_input.setText(file_path)

    def closeEvent(self, event):
        """애플리케이션 종료 시 리소스 정리"""
        # 진행 중인 워커 중단
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(timeout=2000)  # 최대 2초 대기
        
        if self.play_worker and self.play_worker.isRunning():
            self.play_worker.requestInterruption()
            self.play_worker.wait(timeout=1000)  # 최대 1초 대기
        
        # 오디오 캡처 중지
        if self.audio_capture.is_recording:
            self.audio_capture.stop()
        
        # 임시 파일 정리
        if os.path.exists(TEMP_RECORD_FILE):
            try:
                os.remove(TEMP_RECORD_FILE)
            except Exception:
                pass
        
        # 사운드 장치 안전 종료
        try:
            sd.stop()
        except Exception:
            pass
        
        # 이벤트 수락 (정상 종료)
        event.accept()
