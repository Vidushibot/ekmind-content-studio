import json
import subprocess
from pathlib import Path

import imageio_ffmpeg
from backend.schemas.content import Scene, Slide


def build_video_plan(outline: list[Slide]) -> tuple[str, list[Scene]]:
    scenes = [Scene(scene_type="AVATAR_SLIDE" if s.slide_number in {1, len(outline)} else "SLIDE_FULL", spoken_text=s.speaker_notes, slide_number=s.slide_number, avatar_enabled=s.slide_number in {1, len(outline)}) for s in outline]
    return "\n\n".join(s.spoken_text for s in scenes), scenes


def render_mock_video(session_id: str, scenes: list[Scene], slide_previews: list[str], root: Path) -> tuple[Path, Path, dict[str, object]]:
    output = root / "storage" / session_id / "video"; output.mkdir(parents=True, exist_ok=True)
    if len(slide_previews) != len(scenes):
        raise ValueError("Every video scene must have one slide image")
    slide_paths = [Path(path).resolve() for path in slide_previews]
    if not all(path.is_file() and path.suffix.lower() == ".png" for path in slide_paths):
        raise FileNotFoundError("One or more approved slide images are missing")
    (output / "scene_plan.json").write_text(json.dumps([s.model_dump() for s in scenes], indent=2), encoding="utf-8")
    srt = output / "captions.srt"; elapsed = 0; blocks = []
    for i, scene in enumerate(scenes, 1):
        start, end = elapsed, elapsed + int(scene.duration_target); stamp = lambda v: f"00:{v//60:02d}:{v%60:02d},000"
        blocks.append(f"{i}\n{stamp(start)} --> {stamp(end)}\n{scene.spoken_text}\n"); elapsed = end
    srt.write_text("\n".join(blocks), encoding="utf-8")
    video = output / "ekmind-content-video.mp4"
    manifest = output / "slides.ffconcat"
    manifest_lines = ["ffconcat version 1.0"]
    for path, scene in zip(slide_paths, scenes):
        safe_path = path.as_posix().replace("'", "'\\''")
        manifest_lines.extend([f"file '{safe_path}'", f"duration {scene.duration_target:.3f}"])
    manifest_lines.append(f"file '{slide_paths[-1].as_posix()}'")
    manifest.write_text("\n".join(manifest_lines), encoding="utf-8")
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", str(max(8, elapsed)), "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p", "-r", "30", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(video)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    valid = result.returncode == 0 and video.exists() and video.stat().st_size > 0
    validation = {"status": "PASS" if valid else "FAIL", "resolution": "1920x1080", "fps": 30, "audio_stream": valid, "captions": srt.exists(), "provider": "mock", "slide_assets_used": len(slide_paths), "expected_scenes": len(scenes), "composition": "approved_slide_previews"}
    if not valid: raise RuntimeError("Video composition failed")
    return video, srt, validation


def render_heygen_composite(session_id: str, scenes: list[Scene], slide_previews: list[str], avatar_video: Path, duration: float, root: Path) -> tuple[Path, Path, dict[str, object]]:
    """Compose timed slides, transitions, presenter framing, audio, and burned captions."""
    output = root / "storage" / session_id / "video"
    output.mkdir(parents=True, exist_ok=True)
    slide_paths = [Path(path).resolve() for path in slide_previews]
    if len(slide_paths) != len(scenes) or not all(path.is_file() for path in slide_paths):
        raise ValueError("Every video scene must have one approved slide image")
    if not avatar_video.is_file() or avatar_video.stat().st_size == 0:
        raise FileNotFoundError("The HeyGen video could not be downloaded")

    duration = max(8.0, float(duration))
    weights = [max(1, len(scene.spoken_text.split())) for scene in scenes]
    total_weight = sum(weights)
    cue_durations = [duration * weight / total_weight for weight in weights]
    transition = min(0.65, duration / (len(scenes) * 8)) if len(scenes) > 1 else 0.0
    visual_total = duration + transition * (len(scenes) - 1)
    visual_durations = [visual_total * weight / total_weight for weight in weights]

    srt = output / "captions.srt"
    blocks, elapsed, caption_index = [], 0.0, 1
    def stamp(value: float) -> str:
        millis = round(value * 1000); hours, millis = divmod(millis, 3_600_000); minutes, millis = divmod(millis, 60_000); seconds, millis = divmod(millis, 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"
    for scene, scene_duration in zip(scenes, cue_durations):
        words = scene.spoken_text.split()
        chunks = [words[index:index + 8] for index in range(0, len(words), 8)] or [[""]]
        scene_elapsed = 0.0
        for chunk in chunks:
            chunk_duration = scene_duration * len(chunk) / max(1, len(words))
            midpoint = (len(chunk) + 1) // 2
            caption = " ".join(chunk[:midpoint]) + ("\n" + " ".join(chunk[midpoint:]) if midpoint < len(chunk) else "")
            start = elapsed + scene_elapsed
            blocks.append(f"{caption_index}\n{stamp(start)} --> {stamp(start + chunk_duration)}\n{caption}\n")
            caption_index += 1
            scene_elapsed += chunk_duration
        elapsed += scene_duration
    srt.write_text("\n".join(blocks), encoding="utf-8")

    video = output / "ekmind-content-video.mp4"
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y"]
    for path, scene_duration in zip(slide_paths, visual_durations):
        cmd.extend(["-loop", "1", "-t", f"{scene_duration:.3f}", "-i", str(path)])
    avatar_index = len(slide_paths)
    cmd.extend(["-i", str(avatar_video)])

    filters = []
    for index in range(len(slide_paths)):
        filters.append(f"[{index}:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p,setsar=1[s{index}]")
    if len(slide_paths) == 1:
        slides_label = "s0"
    else:
        previous = "s0"
        cumulative = visual_durations[0]
        for index in range(1, len(slide_paths)):
            output_label = f"x{index}"
            offset = cumulative - transition * index
            filters.append(f"[{previous}][s{index}]xfade=transition=fade:duration={transition:.3f}:offset={offset:.3f}[{output_label}]")
            previous = output_label
            cumulative += visual_durations[index]
        slides_label = previous

    intro = min(5.0, max(2.0, cue_durations[0] * 0.65))
    outro = min(5.0, max(2.0, cue_durations[-1] * 0.65))
    middle_end = max(intro, duration - outro)
    filters.extend([
        f"[{avatar_index}:v]split=2[avatarfullsrc][avatarpipsrc]",
        "[avatarfullsrc]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30,format=yuv420p[avatarfull]",
        "[avatarpipsrc]scale=640:-2,fps=30,format=yuv420p[avatarpip]",
        f"[{slides_label}][avatarpip]overlay=W-w-64:H-h-56:enable='between(t\\,{intro:.3f}\\,{middle_end:.3f})'[withpip]",
        f"[withpip][avatarfull]overlay=0:0:enable='lte(t\\,{intro:.3f})+gte(t\\,{middle_end:.3f})'[composed]",
        "[composed]subtitles=filename='captions.srt':force_style='FontName=Arial,FontSize=14,PrimaryColour=&H00FFFFFF,OutlineColour=&H00101010,BorderStyle=1,Outline=1.5,Shadow=0,MarginV=28,Alignment=2'[v]",
    ])
    cmd.extend(["-filter_complex", ";".join(filters), "-map", "[v]", "-map", f"{avatar_index}:a?", "-t", f"{duration:.3f}", "-r", "30", "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart", str(video)])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=900, check=False, cwd=output)
    valid = result.returncode == 0 and video.exists() and video.stat().st_size > 0
    if not valid:
        raise RuntimeError(f"HeyGen slide composition failed: {result.stderr[-500:]}")
    validation = {"status": "PASS", "resolution": "1920x1080", "fps": 30, "audio_stream": True, "captions": "burned_in_and_srt", "caption_style": "compact_two_line", "caption_cues": len(blocks), "provider": "heygen", "slide_assets_used": len(slide_paths), "expected_scenes": len(scenes), "composition": "full_screen_intro_outro_with_large_avatar_pip", "slide_transitions": "crossfade", "timing": "word_weighted_to_heygen_duration", "intro_seconds": round(intro, 2), "outro_seconds": round(outro, 2)}
    return video, srt, validation
