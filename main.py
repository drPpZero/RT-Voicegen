# main.py
"""
VoxCPM2 Realtime Translator & Mic - 진입점

음성 인식 및 번역 기반의 실시간 고속 제어반
"""
import sys
from PyQt6.QtWidgets import QApplication

from core import AIEngine
from ui.main_window import MainWindow


def main():
    """애플리케이션 진입점"""
    app = QApplication(sys.argv)
    
    print("=======================================")
    print("백엔드 엔진 컴파일 중...")
    ai_engine = AIEngine()  # AI 백엔드 엔진 초기화
    print("엔진 준비 완료!")
    print("=======================================")
    
    window = MainWindow(ai_engine)  # 의존성 주입
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
