# workers/ai_processor.py
import numpy as np
import sounddevice as sd
from PyQt6.QtCore import QThread, pyqtSignal

from config import SAMPLE_RATE


class AIProcessingWorker(QThread):
    """AI 고속 연산 처리 스레드"""
    log_signal = pyqtSignal(str)
    result_audio_signal = pyqtSignal(np.ndarray)

    def __init__(self, task_type, audio_data, text_data, config, ai_engine):
        super().__init__()
        self.task_type = task_type          
        self.audio_data = audio_data
        self.text_data = text_data
        self.config = config
        self.ai_engine = ai_engine

    def run(self):
        try:
            target_text = ""
            recognized_text = ""

            # [1] 데이터 전처리 및 STT/번역
            if self.task_type == "text_tts":
                if not self.text_data.strip():
                    self.log_signal.emit("⚠️ 송출할 텍스트를 입력해주세요.")
                    return
                self.log_signal.emit("⏳ [1/2] Nano-vLLM 음성 합성 중...")
                target_text = self.text_data

            elif self.task_type == "voice_translation":
                self.log_signal.emit("⏳ [1/4] Faster-Whisper 고속 음성 인식 중...")
                recognized_text = self.ai_engine.transcribe(
                    self.audio_data, SAMPLE_RATE, self.config['src_code'],
                    interruption_check=self.isInterruptionRequested
                )
                
                if self.isInterruptionRequested(): 
                    raise InterruptedError()
                if not recognized_text:
                    self.log_signal.emit("⚠️ 인식된 텍스트가 없습니다. 다시 말씀해 주세요.")
                    return

                def on_trans_progress(curr, total):
                    if self.isInterruptionRequested(): 
                        raise InterruptedError()
                    self.log_signal.emit(f"⏳ [2/4] 문장 번역 중 ({curr}/{total})...")

                target_text = self.ai_engine.translate(
                    recognized_text, self.config['src_code'], self.config['tgt_code'],
                    on_trans_progress
                )
                self.log_signal.emit(f"📝 번역 완료: {target_text}\n⏳ [3/4] Nano-vLLM 음성 합성 중...")

            if self.isInterruptionRequested(): 
                raise InterruptedError()

            # [2] 음성 합성 (스트리밍 제너레이터 감시 및 즉각 중단 연계)
            wav_chunks = []
            stream = self.ai_engine.synthesize_stream(target_text, self.config)
            try:
                for chunk in stream:
                    if self.isInterruptionRequested():
                        raise InterruptedError()
                    wav_chunks.append(chunk)
            finally:
                if hasattr(stream, 'close'):
                    stream.close()
            
            if not wav_chunks:
                return
            wav = np.concatenate(wav_chunks, axis=0)
            self.result_audio_signal.emit(wav)

            if self.isInterruptionRequested(): 
                raise InterruptedError()

            # [3] 자동 송출 제어
            is_manual = (self.config.get('tx_mode') == "수동")
            output_device = self.config['device']
            
            if output_device != "장치 선택 안함 (미리듣기만)" and not is_manual:
                step_log = "[4/4]" if self.task_type == "voice_translation" else "[2/2]"
                self.log_signal.emit(f"⏳ {step_log} 가상 마이크로 송출 중...")
                
                devices = sd.query_devices()
                dev_id = next((i for i, d in enumerate(devices) if d['name'] == output_device), None)
                if dev_id is not None:
                    sd.play(wav, self.ai_engine.tts_sr, device=dev_id)
                    
                    # sd.wait() 대신 시간 기반 취소 루프 사용
                    duration = len(wav) / self.ai_engine.tts_sr
                    import time
                    start_time = time.time()
                    while time.time() - start_time < duration:
                        if self.isInterruptionRequested():
                            sd.stop()
                            raise InterruptedError()
                        time.sleep(0.1)

            if self.isInterruptionRequested(): 
                raise InterruptedError()

            # [4] 결과 로그 출력
            prefix = "[수동 송출 대기]" if is_manual else "[즉시 송출 완료]"
            if self.task_type == "voice_translation":
                self.log_signal.emit(f"✅ 번역 및 합성 완료 {prefix}\n\n[원문]: {recognized_text}\n[번역]: {target_text}")
            else:
                self.log_signal.emit(f"✅ TTS 생성 완료 {prefix}\n\n[내용]: {target_text}")

        except InterruptedError:
            pass  # 중단 요청 시 예외 처리 없이 종료
        except Exception as e:
            self.log_signal.emit(f"❌ 오류 발생: {str(e)}")
