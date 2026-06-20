# workers/audio_player.py
import sounddevice as sd
from PyQt6.QtCore import QThread, pyqtSignal


class AudioPlayWorker(QThread):
    """수동 오디오 재생 스레드 (UI 멈춤 방지)"""
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)

    def __init__(self, wav_data, sample_rate, device_id):
        super().__init__()
        self.wav_data = wav_data
        self.sample_rate = sample_rate
        self.device_id = device_id

    def run(self):
        try:
            sd.play(self.wav_data, self.sample_rate, device=self.device_id)
            
            # sd.wait() 대신 시간 기반 취소 루프 사용
            duration = len(self.wav_data) / self.sample_rate
            import time
            start_time = time.time()
            is_cancelled = False
            while time.time() - start_time < duration:
                if self.isInterruptionRequested():
                    sd.stop()
                    is_cancelled = True
                    break
                time.sleep(0.1)
                
            if not is_cancelled:
                self.finished_signal.emit()
        except Exception as e:
            self.error_signal.emit(str(e))
