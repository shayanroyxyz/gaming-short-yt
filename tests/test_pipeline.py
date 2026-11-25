import json
import os
import tempfile
import unittest
from unittest.mock import patch

import main
import render_engine


class PipelineRegressionTests(unittest.TestCase):
    def test_groq_model_discovery_excludes_prompt_guard_classifiers(self):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"data": [
                    {"id": "meta-llama/llama-prompt-guard-2-22m", "active": True},
                    {"id": "meta-llama/llama-3.3-70b-versatile", "active": True},
                    {"id": "qwen/qwen3-32b", "active": True},
                    {"id": "meta-llama/llama-guard-4-12b", "active": True},
                    {"id": "gemma2-9b-it", "active": False},
                ]}

        with patch.object(main.requests, "get", return_value=FakeResponse()):
            models = main._discover_groq_models("test-key")

        self.assertIn("meta-llama/llama-3.3-70b-versatile", models)
        self.assertIn("qwen/qwen3-32b", models)
        self.assertNotIn("meta-llama/llama-prompt-guard-2-22m", models)
        self.assertNotIn("meta-llama/llama-guard-4-12b", models)
        self.assertNotIn("gemma2-9b-it", models)

    def test_source_selection_downloads_and_validates_local_clip(self):
        local_clip = "/tmp/gta_source_window.mp4"
        if os.path.exists(local_clip):
            os.remove(local_clip)

        with tempfile.TemporaryDirectory() as home:
            with patch.dict(os.environ, {"HOME": home, "RCLONE_CONF": "[test]\ntype = local\n"}):
                ffprobe_results = iter(("90.0", "65.0"))

                def fake_check_output(cmd, **kwargs):
                    if cmd[:2] == ["rclone", "lsjson"]:
                        if cmd[2].startswith("mega:"):
                            return json.dumps([{"Name": "[GTA6]_Clip_42.mp4", "IsDir": False}])
                        return "[]"
                    if cmd[0] == "ffprobe":
                        return next(ffprobe_results)
                    raise AssertionError(f"Unexpected command: {cmd}")

                def fake_run(cmd, **kwargs):
                    if cmd[:2] == ["rclone", "copyto"]:
                        with open(cmd[3], "wb") as out:
                            out.write(b"x" * 200_000)
                    elif cmd[0] == "ffmpeg":
                        self.assertIn("65.0", cmd)
                        with open(cmd[-1], "wb") as out:
                            out.write(b"y" * 200_000)
                    else:
                        raise AssertionError(f"Unexpected command: {cmd}")
                    return type("Result", (), {"returncode": 0})()

                with patch.object(main.subprocess, "check_output", side_effect=fake_check_output), \
                     patch.object(main.subprocess, "run", side_effect=fake_run), \
                     patch.object(main.random, "choice", side_effect=lambda values: values[0]):
                    history = {"used_windows": [], "used_topics": []}
                    result = main.stream_unique_action_clips(history, "gta6")

                fname, selected_path, source_hash, start_second, source_duration, source_key = result
                self.assertEqual(fname, "[GTA6]_Clip_42.mp4")
                self.assertEqual(selected_path, local_clip)
                self.assertTrue(os.path.isfile(selected_path))
                self.assertEqual(len(source_hash), 64)
                self.assertEqual(start_second, 0.0)
                self.assertEqual(source_duration, 65.0)
                self.assertEqual(source_key, "mega:[GTA6]_Clip_42.mp4")
                self.assertIn("mega:[GTA6]_Clip_42.mp4@0s", history["used_sources"])

        if os.path.exists(local_clip):
            os.remove(local_clip)

    def _run_renderer_fixture(self, metric_by_start, audio_duration=24.0):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        source = os.path.join(tmp.name, "source.mp4")
        voice = os.path.join(tmp.name, "voice.mp3")
        output = os.path.join(tmp.name, "final.mp4")
        with open(source, "wb") as f:
            f.write(b"s" * 200_000)
        with open(voice, "wb") as f:
            f.write(b"v" * 10_000)

        captured = {}

        def fake_run(cmd, **kwargs):
            with open(cmd[-1], "wb") as f:
                f.write(b"o" * 200_000)
            if "-filter_complex" in cmd:
                graph = cmd[cmd.index("-filter_complex") + 1]
                captured["graph"] = graph
                time_values = [cmd[i + 1] for i, value in enumerate(cmd[:-1]) if value == "-t"]
                self.assertEqual(time_values[-1], str(audio_duration))
                self.assertIn("scale=1080:1920:force_original_aspect_ratio=increase", graph)
                self.assertIn("crop=1080:1920", graph)
                self.assertNotIn("gblur=", graph)
                self.assertIn("drawtext=", graph)
            else:
                self.assertIn("-filter:a", cmd)
                self.assertIn("atempo=1.0", cmd)
            return type("Result", (), {"returncode": 0})()

        def fake_metrics(_src, start, _duration):
            return metric_by_start[float(start)]

        with patch.object(render_engine, "synthesize_human_voice",
                          return_value=(voice, audio_duration, "en-US-AndrewMultilingualNeural")), \
             patch.object(render_engine, "build_clean_ass_captions",
                          return_value=os.path.join(tmp.name, "captions.ass")), \
             patch.object(render_engine, "_score_motion_windows",
                          return_value=list(metric_by_start.keys())), \
             patch.object(render_engine, "_opening_window_metrics", side_effect=fake_metrics), \
             patch.object(render_engine.subprocess, "check_output", side_effect=["65.0", str(audio_duration)]), \
             patch.object(render_engine.subprocess, "run", side_effect=fake_run):
            result = render_engine.render_full_bleed_short(
                source, "A current length test narration.", output,
                top_hook="WATCH THIS STUNT"
            )

        self.assertEqual(result, output)
        self.assertTrue(os.path.isfile(output))
        return captured["graph"]

    @staticmethod
    def _metrics(motion, accepted, luma=128.0, contrast=55.0, saturation=90.0):
        quality_ok = luma >= 85 and saturation >= 35 and contrast >= 38
        return {
            "mean_luma": luma,
            "min_frame_luma": luma,
            "saturation": saturation,
            "contrast": contrast,
            "motion": motion,
            "quality_ok": quality_ok,
            "accepted": accepted,
        }

    def test_renderer_scales_cuts_for_short_and_long_narrations(self):
        short_graph = self._run_renderer_fixture({
            0.0: self._metrics(18.0, True),
            4.0: self._metrics(16.0, True),
        }, audio_duration=14.01)
        self.assertIn("concat=n=4:v=1:a=0", short_graph)

        long_graph = self._run_renderer_fixture({
            0.0: self._metrics(18.0, True),
            4.0: self._metrics(16.0, True),
        }, audio_duration=58.5)
        self.assertIn("concat=n=17:v=1:a=0", long_graph)
        self.assertIn("duration=0.35", long_graph)
        self.assertIn("sidechaincompress=", long_graph)
        self.assertIn("acrossfade=d=0.35", long_graph)

    def test_ai_parser_accepts_natural_96_word_narration(self):
        script = " ".join(
            [f"Detail{i}" for i in range(1, 97)]
        ) + "."
        payload = {
            "hook": "HIDDEN GAME DETAIL",
            "script": script,
            "title": "GTA 6: The Hidden Truth?",
            "comment": "Did you notice it?",
            "creative_angle": "story_fact",
        }
        parsed = main._parse_strict_ai_json(json.dumps(payload))
        self.assertEqual(len(parsed["script"].split()), 96)

    def test_renderer_uses_best_combined_visual_fallback_without_quality_floor(self):
        graph = self._run_renderer_fixture({
            0.0: self._metrics(10.0, False, luma=200.0, contrast=80.0, saturation=18.0),
            4.0: self._metrics(45.0, False, luma=60.0, contrast=50.0, saturation=12.0),
            8.0: self._metrics(25.0, False, luma=120.0, contrast=60.0, saturation=25.0),
        })
        self.assertIn("[0:v]trim=start=0.000", graph)

    def test_visual_score_prefers_brightness_contrast_motion_balance(self):
        bright = self._metrics(10.0, False, luma=200.0, contrast=80.0, saturation=18.0)
        dark_fast = self._metrics(45.0, False, luma=60.0, contrast=50.0, saturation=12.0)
        self.assertGreater(
            render_engine._visual_window_score(bright),
            render_engine._visual_window_score(dark_fast),
        )

    def test_caption_chunks_use_72px_centered_word_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "captions.ass")
            script = "One two three four five six seven eight"
            boundaries = [
                {"text": word, "start": i * 0.3, "duration": 0.2}
                for i, word in enumerate(script.split())
            ]
            render_engine.build_clean_ass_captions(script, 3.0, path, boundaries)
            with open(path, encoding="utf-8") as caption_file:
                content = caption_file.read()

            self.assertIn("Style: PopCap,DejaVu Sans,72,", content)
            self.assertIn(",70,70,0,1", content)
            self.assertIn(r"\an5\pos(540,1050)", content)
            self.assertIn(r"\fscx100", content)
            self.assertIn("Dialogue: 0,0:00:00.00,0:00:00.80", content)
            self.assertNotIn(r"\N", content)


if __name__ == "__main__":
    unittest.main()
