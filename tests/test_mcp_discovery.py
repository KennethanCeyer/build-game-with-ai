import subprocess
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_mcp_server_is_runnable_as_module():
    """MCP 서버가 독립 프로세스로(python -m ...) 실행 가능한지 확인합니다."""
    # handson 모드로 테스트
    env = dict(os.environ)
    src_path = str(ROOT / "src")
    lab_path = str(ROOT / "handson")
    
    # PYTHONPATH 설정 시뮬레이션
    env["PYTHONPATH"] = os.pathsep.join([src_path, lab_path])
    
    # --help 옵션으로 실행하여 모듈 로드 및 기본 인자 파싱 확인
    # 성공하면 0 또는 에러(인자 부족)가 나더라도 모듈 로드 실패(1)는 아니어야 함.
    # FastMCP는 보통 인자 없이 실행하면 서버를 띄우려 하므로, 
    # 여기서는 단순히 import 에러가 안 나는지만 확인하기 위해 짧게 실행함.
    
    cmd = [sys.executable, "-m", "game_agent.mcp_server", "--help"]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    
    # 'No module named' 에러가 없어야 함
    assert "No module named" not in result.stderr
    # FastMCP/Click 관련 도움말이 출력되거나, 최소한 임포트 성공 증거가 있어야 함
    assert result.returncode == 0 or "Usage:" in result.stdout or "Usage:" in result.stderr

def test_mcp_server_is_runnable_as_module_solution():
    """정답 모드에서도 MCP 서버가 실행 가능한지 확인합니다."""
    env = dict(os.environ)
    src_path = str(ROOT / "src")
    lab_path = str(ROOT / "solution")
    
    env["PYTHONPATH"] = os.pathsep.join([src_path, lab_path])
    
    cmd = [sys.executable, "-m", "game_agent.mcp_server", "--help"]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    
    assert "No module named" not in result.stderr
    assert result.returncode == 0 or "Usage:" in result.stdout or "Usage:" in result.stderr
