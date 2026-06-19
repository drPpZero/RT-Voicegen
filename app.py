import gradio as gr
import sounddevice as sd
import soundfile as sf
import numpy as np
from voxcpm import VoxCPM

# 1. 모델 로드 (전역 메모리에 최초 1회 적재)
print("VoxCPM2 모델을 불러오는 중입니다. 잠시만 기다려주세요...")
model = VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False)
print("모델 로드 완료!")

# 2. 시스템 오디오 출력 장치 목록 가져오기
def get_audio_devices():
    devices = sd.query_devices()
    # 출력 채널이 있는 장치(스피커, 가상 케이블 입력 등)만 필터링
    output_devices = [dev['name'] for dev in devices if dev['max_output_channels'] > 0]
    return ["장치 선택 안함 (미리듣기만)"] + output_devices

# 오디오 장치로 실제 재생/송출을 담당하는 공통 함수
def play_audio(wav, sample_rate, output_device):
    if output_device == "장치 선택 안함 (미리듣기만)" or wav is None:
        return
        
    devices = sd.query_devices()
    device_id = next((i for i, d in enumerate(devices) if d['name'] == output_device), None)
    
    if device_id is not None:
        print(f"[{output_device}] 장치로 오디오 송출 중...")
        sd.play(wav, sample_rate, device=device_id)
        sd.wait() # 오디오 재생이 끝날 때까지 대기
    else:
        print("선택한 오디오 장치를 찾을 수 없습니다.")

# 3. 음성 생성 및 즉시 송출 로직
def process_tts(text, mode, voice_prompt, ref_audio_path, output_device, tx_mode, cfg_value, timesteps):
    if not text.strip():
        return None, None
        
    sample_rate = model.tts_model.sample_rate
    
    # [모드 1] 보이스 클로닝
    if mode == "보이스 클로닝" and ref_audio_path:
        wav = model.generate(
            text=text,
            ref_audio=ref_audio_path,
            cfg_value=float(cfg_value),
            inference_timesteps=int(timesteps)
        )
    # [모드 2] 텍스트 프롬프트 기반 음성 디자인
    else:
        prompt = f"({voice_prompt}){text}"
        wav = model.generate(
            text=prompt,
            cfg_value=float(cfg_value),
            inference_timesteps=int(timesteps)
        )

    # 마이크 송출 방식이 '즉시 송출'인 경우 생성되자마자 가상 마이크로 전달
    if tx_mode == "즉시 송출":
        play_audio(wav, sample_rate, output_device)
                
    # 웹 UI 미리듣기 플레이어와 내부 State 저장소에 동시에 오디오 데이터 전달
    return (sample_rate, wav), (sample_rate, wav)

# 4. 수동 송출 버튼 클릭 시 동작하는 로직
def manual_send(audio_state, output_device):
    if audio_state is None:
        return "⚠️ 송출할 음성이 없습니다. 먼저 음성을 생성해주세요."
    
    sample_rate, wav = audio_state
    play_audio(wav, sample_rate, output_device)
    return "✅ 가상 마이크로 송출을 완료했습니다!"

# 5. Gradio 웹 UI 구성
with gr.Blocks(title="VoxCPM2 Realtime Mic") as app:
    gr.Markdown("# 🎙️ VoxCPM2 실시간 보이스 클로닝 & 마이크 송출기")
    gr.Markdown("오픈소스 가상 오디오 케이블(VB-Cable 등)을 활용해 생성된 AI 음성을 실시간 마이크 입력으로 라우팅하는 웹 인터페이스입니다.")
    
    # 생성된 오디오 데이터를 임시 보관할 숨겨진 메모리 공간
    current_audio_state = gr.State(None)
    
    with gr.Row():
        with gr.Column(scale=2):
            text_input = gr.Textbox(label="할 말 (텍스트 입력)", lines=4, placeholder="상대방에게 전달할 내용을 입력하세요.")
            
            mode_radio = gr.Radio(
                choices=["보이스 디자인", "보이스 클로닝"], 
                value="보이스 디자인", 
                label="생성 모드 선택"
            )
            
            with gr.Group():
                voice_prompt = gr.Textbox(label="목소리 스타일 프롬프트 (보이스 디자인용)", value="A calm and clear male voice")
                ref_audio = gr.Audio(label="레퍼런스 오디오 (보이스 클로닝용, 3~5초 권장)", type="filepath")
                
            device_dropdown = gr.Dropdown(
                choices=get_audio_devices(), 
                value="장치 선택 안함 (미리듣기만)", 
                label="오디오 송출 장치 (가상 오디오 케이블 선택)"
            )
            
            tx_mode_radio = gr.Radio(
                choices=["즉시 송출", "수동 송출 (버튼 클릭)"],
                value="즉시 송출",
                label="마이크 송출 방식 설정"
            )
            
            # 고급 모델 설정 (접고 펼칠 수 있는 아코디언 메뉴)
            with gr.Accordion("⚙️ 고급 모델 파라미터 설정", open=False):
                cfg_slider = gr.Slider(
                    minimum=1.0, maximum=5.0, value=2.0, step=0.1, 
                    label="CFG Scale (프롬프트 강조도 - 높을수록 설정한 목소리 성향 강해짐)"
                )
                timesteps_slider = gr.Slider(
                    minimum=5, maximum=50, value=10, step=1, 
                    label="Inference Timesteps (추론 단계 수 - 낮을수록 빠름, 높을수록 음질 향상)"
                )
            
            # 하단 제어 버튼 배치
            with gr.Row():
                gen_btn = gr.Button("음성 생성 ⚡", variant="primary")
                send_btn = gr.Button("마이크로 송출 🎙️", variant="secondary")
                
            # 상태 안내 출력 창
            status_output = gr.Markdown("")
            
        with gr.Column(scale=1):
            audio_preview = gr.Audio(label="생성된 음성 미리듣기", type="numpy")

    # [이벤트 1] 음성 생성 버튼 클릭 시 로직 연결
    gen_btn.click(
        fn=process_tts, 
        inputs=[
            text_input, mode_radio, voice_prompt, ref_audio, 
            device_dropdown, tx_mode_radio, cfg_slider, timesteps_slider
        ], 
        outputs=[audio_preview, current_audio_state]
    )
    
    # [이벤트 2] 수동 송출 버튼 클릭 시 로직 연결
    send_btn.click(
        fn=manual_send,
        inputs=[current_audio_state, device_dropdown],
        outputs=status_output
    )

if __name__ == "__main__":
    # 실행 시 브라우저 창이 자동으로 열리도록 설정
    app.launch(inbrowser=True)