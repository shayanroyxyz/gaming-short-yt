import json
import os
import tempfile
import unittest
from unittest.mock import patch

import main
import render_engine


class PipelineRegressionTests(unittest.TestCase):
    def test_source_selection_downloads_and_validates_local_clip(self):
        old_clip = "/tmp/gta_source_clip.mp4"
        if os.path.exists(old_clip):
            os.remove(old_clip)

        with tempfile.TemporaryDirectory() as home:
            with patch.dict(os.environ, {"HOME": home, "RCLONE_CONF": "[test]\ntype = local\n"}):
                def fake_check_output(cmd, **kwargs):
                    if cmd[:2] == ["rclone", "lsjson"]:
                        if cmd[2].startswith("mega:"):
                            return json.dumps([{"Name": "[GTA6]_Clip_42.mp4", "IsDir": False}])
                        return "[]"
                    if cmd[0] == "ffprobe":
                        return "42.0"
                    raise AssertionError(f"Unexpected command: {cmd}")

                def fake_run(cmd, **kwargs):
                    self.assertEqual(cmd[:2], ["rclone", "copyto"])
                    with open(cmd[3], "wb") as out:
                        out.write(b"x" * 200_000)
                    return type("Result", (), {"returncode": 0})()

                with patch.object(main.subprocess, "check_output", side_effect=fake_check_output), \
                     patch.object(main.subprocess, "run", side_effect=fake_run):
                    history = {"used_windows": [], "used_topics": []}
                    fname, local_path, source_hash, start_second, source_duration = main.stream_unique_action_clips(history, "gta6")

                self.assertEqual(fname, "[GTA6]_Clip_42.mp4")
                self.assertEqual(local_path, old_clip)
                self.assertTrue(os.path.isfile(local_path))
                self.assertEqual(len(source_hash), 64)
                self.assertEqual(start_second, 0.0)
                self.assertEqual(source_duration, 42.0)
                self.assertIn("mega:[GTA6]_Clip_42.mp4", history["used_sources"])

        if os.path.exists(old_clip):
            os.remove(old_clip)

    def test_renderer_builds_full_bleed_vertical_crop_and_exact_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source.mp4")
            voice = os.path.join(tmp, "voice.mp3")
            output = os.path.join(tmp, "final.mp4")
            with open(source, "wb") as f:
                f.write(b"s" * 200_000)
            with open(voice, "wb") as f:
                f.write(b"v" * 10_000)

            def fake_run(cmd, **kwargs):
                with open(cmd[-1], "wb") as f:
                    f.write(b"o" * 200_000)
                if "-filter_complex" in cmd:
                    self.assertIn("-t", cmd)
                    self.assertEqual(cmd[cmd.index("-t") + 1], "14.4")
                    graph = cmd[cmd.index("-filter_complex") + 1]
                    self.assertIn("concat=n=2:v=1:a=0", graph)
                    self.assertIn("duration=7.2", graph)
                    self.assertIn("scale=1080:1920:force_original_aspect_ratio=increase", graph)
                    self.assertIn("crop=1080:1920", graph)
                    self.assertNotIn("gblur=", graph)
                    self.assertNotIn("pad=1080:608", graph)
                    self.assertNotIn("overlay=(W-w)/2:(H-h)/2", graph)
                    self.assertIn("drawtext=", graph)
                else:
                    self.assertIn("-filter:a", cmd)
                    self.assertIn("atempo=1.000000", cmd)
                return type("Result", (), {"returncode": 0})()

            with patch.object(render_engine, "synthesize_human_voice",
                              return_value=(voice, 14.05, "en-US-AndrewMultilingualNeural")), \
                 patch.object(render_engine, "build_clean_ass_captions", return_value=os.path.join(tmp, "captions.ass")), \
                 patch.object(render_engine.subprocess, "check_output", side_effect=["30.0", "14.4"]), \
                 patch.object(render_engine.subprocess, "run", side_effect=fake_run):
                result = render_engine.render_full_bleed_short(
                    source, "A short test script.", output, top_hook="WATCH THIS STUNT"
                )

            self.assertEqual(result, output)
            self.assertTrue(os.path.isfile(output))

    def test_caption_chunks_use_word_boundaries_and_pop_style(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "captions.ass")
            script = "One two three four five six seven eight"
            boundaries = [{"text": word, "start": i * 0.3, "duration": 0.2}
                           for i, word in enumerate(script.split())]
            render_engine.build_clean_ass_captions(script, 3.0, path, boundaries)
            with open(path, encoding="utf-8") as caption_file:
                content = caption_file.read()
            self.assertIn(",70,70,230,1", content)
            self.assertIn("80,\\fscx100", content)
            self.assertIn("\\N", content)
            self.assertIn("Dialogue: 0,0:00:00.00,0:00:01.10", content)


if __name__ == "__main__":
    unittest.main()
