import time
import pytest
from app.services.idle_detector import IdleDetector

def test_idle_detector_thresholds():
    detector = IdleDetector(check_interval_seconds=0.1)
    
    # Not started, is_idle is False
    assert detector.is_idle() is False
    
    # Start with a 0.3s window
    detector.start(threshold_cpu=100.0, idle_window_seconds=0.3)
    
    # Initially should be false until window is filled
    assert detector.is_idle() is False
    
    time.sleep(0.4)
    # Since threshold is 100%, and window is filled, it should be true
    assert detector.is_idle() is True
    
    detector.update_config(threshold_cpu=-1.0, idle_window_seconds=0.3)
    time.sleep(0.4)
    # Threshold is -1%, so readings will be > threshold -> not idle
    assert detector.is_idle() is False
    
    detector.stop()
