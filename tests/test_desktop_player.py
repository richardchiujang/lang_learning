# test_desktop_player.py

import sys
import types
import pytest
from unittest.mock import MagicMock, patch

# Absolute import for namespace package
from desktop_player import LanguagePlayer

@pytest.fixture
def player(qtbot):
    # Patch PySide6 widgets to avoid real UI
    with patch("desktop_player.QMainWindow.__init__", lambda self: None), \
         patch("desktop_player.QWidget"), \
         patch("desktop_player.QVBoxLayout"), \
         patch("desktop_player.QHBoxLayout"), \
         patch("desktop_player.QLabel"), \
         patch("desktop_player.QPushButton"), \
         patch("desktop_player.QSlider"), \
         patch("desktop_player.QComboBox"), \
         patch("desktop_player.QFrame"), \
         patch("desktop_player.QSizePolicy"), \
         patch("desktop_player.QListWidget"), \
         patch("desktop_player.QMediaPlayer"), \
         patch("desktop_player.QAudioOutput"), \
         patch("desktop_player.QVideoWidget"), \
         patch("desktop_player.QUrl"), \
         patch("desktop_player.Qt"), \
         patch("desktop_player.QTime"):
        p = LanguagePlayer.__new__(LanguagePlayer)
        # Minimal mock for required attributes
        p.lbl_en = MagicMock()
        p.lbl_zh = MagicMock()
        p.show_subtitle_en = True
        p.show_subtitle_zh = True
        return p

def test_update_subtitle_word_level(player):
    # Segment with word-level timestamps, current time matches a word
    player.segments = [{
        'start_time': 0,
        'end_time': 2,
        'text_en': 'Hello world',
        'text_zh': '哈囉世界',
        'keywords': ['world'],
        'words': [
            {'word': 'Hello', 'start': 0, 'end': 1},
            {'word': 'world', 'start': 1, 'end': 2}
        ]
    }]
    # Current time: 1500ms (should highlight 'world')
    player.update_subtitle(1500)
    en_html = player.lbl_en.setText.call_args[0][0]
    zh_html = player.lbl_zh.setText.call_args[0][0]
    assert "FFD700" in en_html  # gold highlight for current word
    assert "world" in en_html
    assert "FFD700" in zh_html  # gold highlight for current char

def test_update_subtitle_progress_fallback(player):
    # Segment without word-level timestamps
    player.segments = [{
        'start_time': 0,
        'end_time': 2,
        'text_en': 'foo bar baz',
        'text_zh': '甲乙丙',
        'keywords': ['bar']
    }]
    # Current time: 1000ms (middle of segment, should highlight 'bar')
    player.update_subtitle(1000)
    en_html = player.lbl_en.setText.call_args[0][0]
    assert "bar" in en_html
    assert "#FF4444" in en_html  # keyword highlight

def test_update_subtitle_no_segment_found(player):
    # No segment matches current time
    player.segments = [{
        'start_time': 0,
        'end_time': 1,
        'text_en': 'test',
        'text_zh': '測試'
    }]
    # Current time: 2000ms (no segment)
    player.lbl_en.reset_mock()
    player.lbl_zh.reset_mock()
    player.update_subtitle(2000)
    # Should not call setText
    assert not player.lbl_en.setText.called or player.lbl_en.setText.call_args[0][0] == ""
    assert not player.lbl_zh.setText.called or player.lbl_zh.setText.call_args[0][0] == ""

def test_update_subtitle_toggle_visibility(player):
    # Segment present
    player.segments = [{
        'start_time': 0,
        'end_time': 2,
        'text_en': 'foo bar',
        'text_zh': '甲乙'
    }]
    # Hide English subtitle
    player.show_subtitle_en = False
    player.show_subtitle_zh = True
    player.update_subtitle(1000)
    assert player.lbl_en.setText.call_args[0][0] == ""
    assert player.lbl_zh.setText.call_args[0][0] != ""

    # Hide Chinese subtitle
    player.show_subtitle_en = True
    player.show_subtitle_zh = False
    player.update_subtitle(1000)
    assert player.lbl_en.setText.call_args[0][0] != ""
    assert player.lbl_zh.setText.call_args[0][0] == ""

def test_update_subtitle_keyword_highlight(player):
    # Segment with keyword
    player.segments = [{
        'start_time': 0,
        'end_time': 2,
        'text_en': 'alpha beta gamma',
        'text_zh': '阿貝伽',
        'keywords': ['beta']
    }]
    player.update_subtitle(1000)
    en_html = player.lbl_en.setText.call_args[0][0]
    assert "beta" in en_html
    assert "#FF4444" in en_html  # keyword highlight