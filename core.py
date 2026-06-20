# core.py
import os
import tempfile
import numpy as np
import torch
import sounddevice as sd
import soundfile as sf
from deep_translator import GoogleTranslator
from faster_whisper import WhisperModel
from voxcpm import VoxCPM

# 동적 Argos Translate 가용성 체크
try:
    import argostranslate.package
    import argostranslate.translate
    ARGOS_AVAILABLE = True
except ImportError:
    ARGOS_AVAILABLE = False

class AudioCapture:
    """마이크 입력을 배열 버퍼로 캡처하는 통합 컨트롤러"""
    def __init__(self, sample_rate):
        self.sample_rate = sample_rate
        self.buffer = []
        self.stream = None
        self.is_recording = False

    def audio_callback(self, indata, frames, time, status):
        if self.is_recording:
            self.buffer.append(indata.copy())

    def start(self):
        self.buffer = []
        self.stream = sd.InputStream(samplerate=self.sample_rate, channels=1, callback=self.audio_callback)
        self.stream.start()
        self.is_recording = True

    def stop(self):
        self.is_recording = False
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        
        audio_out = None
        if self.buffer:
            audio_out = np.concatenate(self.buffer, axis=0)
        self.buffer = [] # 메모리 누수 방지
        return audio_out

class AIEngine:
    """STT, 번역, TTS 모델을 단일 인터페이스로 관리하는 백엔드 엔진"""
    def __init__(self):
        # GPU 가속 자동 감지 및 양자화 타겟 지정
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        print(f"⚙️ 실시간 엔진 로드 - Device: {device}, STT Compute Type: {compute_type}")
        
        self.stt_model = WhisperModel("base", device=device, compute_type=compute_type)
        self.tts_model = VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False)
        self.translator = GoogleTranslator()
        self.tts_sr = self.tts_model.tts_model.sample_rate

    def get_supported_languages(self):
        return self.translator.get_supported_languages(as_dict=True)

    def _ensure_v2_or_reload(self):
        """Runtime: ensure the underlying model is VoxCPM2; attempt reload once if not."""
        try:
            from voxcpm.model.voxcpm2 import VoxCPM2Model
        except Exception:
            return True
        wrapper = self.tts_model
        try:
            inner = getattr(wrapper, 'tts_model', None)
        except Exception:
            inner = None
        if isinstance(inner, VoxCPM2Model):
            return True
        if inner is not None and inner.__class__.__name__ == "VoxCPM2Model":
            return True
        if inner is not None and "voxcpm2" in getattr(inner.__class__, "__module__", ""):
            return True
        try:
            print("⚠️ 현재 로드된 TTS가 VoxCPM2가 아닙니다. VoxCPM2를 다시 로드합니다...")
            self.tts_model = VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False)
            inner = getattr(self.tts_model, 'tts_model', None)
            return isinstance(inner, VoxCPM2Model)
        except Exception as e:
            print(f"❌ VoxCPM2 재로딩 실패: {e}")
            return False

    def transcribe(self, audio_data, sample_rate, lang_code, interruption_check=None):
        """Faster-Whisper를 이용한 STT 처리 (디스크 I/O 배제 및 성능 최적화)"""
        if audio_data is None or len(audio_data) == 0:
            return ""
        
        # 1차원 평탄화 및 float32 변환
        if len(audio_data.shape) > 1:
            audio_data = np.squeeze(audio_data)
        audio_data = audio_data.astype(np.float32)
        
        # 오디오 레벨 정규화
        max_val = np.max(np.abs(audio_data))
        if max_val > 1.0:
            audio_data = audio_data / max_val
            
        whisper_lang = lang_code.split('-')[0] if lang_code != "auto" else None
        # Explicitly disable retry on bad cases to avoid warnings when in streaming mode
        segments, _ = self.stt_model.transcribe(
            audio_data,
            language=whisper_lang,
            beam_size=3,
            vad_filter=True
        )
        
        texts = []
        for s in segments:
            if interruption_check and interruption_check():
                raise InterruptedError()
            texts.append(s.text)
        return "".join(texts).strip()

    def translate(self, text, src_code, tgt_code, progress_callback=None):
        """단일 블록 텍스트 번역 — separator 기능 제거됨"""
        # 간단한 진행 콜백(1/1)
        if progress_callback:
            try:
                progress_callback(1, 1)
            except Exception:
                pass

        # 1. Argos Translate 로컬 번역 시도
        if ARGOS_AVAILABLE:
            try:
                s_code = src_code.split('-')[0]
                t_code = tgt_code.split('-')[0]

                installed_languages = argostranslate.translate.get_installed_languages()
                from_lang = list(filter(lambda x: x.code == s_code, installed_languages))
                to_lang = list(filter(lambda x: x.code == t_code, installed_languages))

                if from_lang and to_lang:
                    translation_model = from_lang[0].get_translation(to_lang[0])
                    if translation_model:
                        trans_text = translation_model.translate(text)
                        print("📡 [오프라인 가속] Argos 로컬 번역 수행 완료")
                        return trans_text
            except Exception as argos_err:
                print(f"⚠️ Argos 로컬 번역 실패 (GoogleTranslator로 폴백): {argos_err}")

        # 2. 폴백: 기존 GoogleTranslator API 사용
        translator = GoogleTranslator(source=src_code, target=tgt_code)
        return translator.translate(text)

    def synthesize(self, target_text, config):
        """Nano-vLLM (VoxCPM) 기반 음성 합성"""
        mode = config.get('mode', "보이스 디자인")
        # 클로닝 전용
        if mode == "보이스 클로닝":
            if not os.path.exists(config['ref_path']):
                raise FileNotFoundError(f"클로닝 레퍼런스 파일 누락: {config['ref_path']}")
            if not self._ensure_v2_or_reload():
                raise RuntimeError("reference_wav_path requires VoxCPM2 model. 모델 로드 상태를 확인하세요.")
            return self.tts_model.generate(
                text=target_text,
                reference_wav_path=config['ref_path'],
                cfg_value=config['cfg'],
                inference_timesteps=config['steps']
            )
        # 하이브리드: 프롬프트와 레퍼런스를 함께 사용
        elif mode == "보이스 하이브리드":
            if not os.path.exists(config['ref_path']):
                raise FileNotFoundError(f"클로닝 레퍼런스 파일 누락: {config['ref_path']}")
            prompt_text = f"({config['prompt']}){target_text}"
            if not self._ensure_v2_or_reload():
                raise RuntimeError("reference_wav_path requires VoxCPM2 model. 모델 로드 상태를 확인하세요.")
            return self.tts_model.generate(
                text=prompt_text,
                reference_wav_path=config['ref_path'],
                cfg_value=config['cfg'],
                inference_timesteps=config['steps']
            )
        # 기본: 프롬프트 기반 디자인
        else:
            prompt_text = f"({config['prompt']}){target_text}"
            return self.tts_model.generate(
                text=prompt_text,
                cfg_value=config['cfg'],
                inference_timesteps=config['steps']
            )

    def synthesize_stream(self, target_text, config):
        """Nano-vLLM (VoxCPM) 기반 음성 합성 스트리밍 제너레이터"""
        mode = config.get('mode', "보이스 디자인")
        if mode == "보이스 클로닝":
            if not os.path.exists(config['ref_path']):
                raise FileNotFoundError(f"클로닝 레퍼런스 파일 누락: {config['ref_path']}")
            if not self._ensure_v2_or_reload():
                raise RuntimeError("reference_wav_path requires VoxCPM2 model. 모델 로드 상태를 확인하세요.")
            return self.tts_model.generate_streaming(
                text=target_text,
                reference_wav_path=config['ref_path'],
                cfg_value=config['cfg'],
                inference_timesteps=config['steps']
            )
        elif mode == "보이스 하이브리드":
            if not os.path.exists(config['ref_path']):
                raise FileNotFoundError(f"클로닝 레퍼런스 파일 누락: {config['ref_path']}")
            prompt_text = f"({config['prompt']}){target_text}"
            if not self._ensure_v2_or_reload():
                raise RuntimeError("reference_wav_path requires VoxCPM2 model. 모델 로드 상태를 확인하세요.")
            return self.tts_model.generate_streaming(
                text=prompt_text,
                reference_wav_path=config['ref_path'],
                cfg_value=config['cfg'],
                inference_timesteps=config['steps']
            )
        else:
            prompt_text = f"({config['prompt']}){target_text}"
            return self.tts_model.generate_streaming(
                text=prompt_text,
                cfg_value=config['cfg'],
                inference_timesteps=config['steps']
            )