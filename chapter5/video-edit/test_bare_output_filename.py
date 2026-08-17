import os
import make_test_video
from video_editor import apply_edit


def test_make_test_video_bare_filename():
    out_name = "test_temp_bare_video.mp4"
    if os.path.exists(out_name):
        os.remove(out_name)
    try:
        path = make_test_video.make(out_name)
        assert os.path.exists(path)
        assert path == out_name
    finally:
        if os.path.exists(out_name):
            os.remove(out_name)
        for i in range(len(make_test_video.SCENES)):
            scene_file = f"_scene_{i}.mp4"
            if os.path.exists(scene_file):
                os.remove(scene_file)


def test_apply_edit_bare_filename():
    source = "test_source.mp4"
    make_test_video.make(source)
    out_name = "test_output_bare_video.mp4"
    if os.path.exists(out_name):
        os.remove(out_name)
    plan = {
        "start": 0.0,
        "end": 2.0,
        "effects": [{"type": "subtitle", "text": "hello"}],
    }
    try:
        path = apply_edit(source, plan, out_name, backend="ffmpeg")
        assert os.path.exists(path)
        assert path == out_name
    finally:
        for name in (out_name, source, "edit.py"):
            if os.path.exists(name):
                os.remove(name)
        for i in range(len(make_test_video.SCENES)):
            scene_file = f"_scene_{i}.mp4"
            if os.path.exists(scene_file):
                os.remove(scene_file)
