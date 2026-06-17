import os
import asyncio
import json
import tempfile
from pathlib import Path
from typing import Tuple, List
from app.config import FFMPEG_PATH, FFPROBE_PATH

async def get_audio_duration(audio_path: str) -> float:
    """Gets audio duration in seconds using ffprobe asynchronously."""
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
    cmd = [
        FFPROBE_PATH, '-v', 'quiet',
        '-print_format', 'json',
        '-show_format', audio_path
    ]
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    
    if process.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {stderr.decode()}")
        
    data = json.loads(stdout.decode())
    return float(data['format']['duration'])

async def assemble_video(
    project_dir: str,
    resolution: str = '1920x1080',
    fps: int = 30,
    zoom_speed: float = 0.0008,
    progress_callback = None
) -> str:
    """
    Assembles final video from scenes/ directory and voice.mp3.
    Uses zoompan and scaling filters.
    
    Args:
        project_dir: Absolute path of project.
        resolution: Output dimensions (e.g. '1920x1080' or '1080x1920' for Shorts).
        fps: Frames per second.
        zoom_speed: Velocity of zoom effect.
        progress_callback: Async function taking an integer percent (0-100).
    """
    audio_path = os.path.join(project_dir, 'voice.mp3')
    scenes_dir = os.path.join(project_dir, 'scenes')
    output_path = os.path.join(project_dir, 'final_video.mp4')
    
    # 1. Validation
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Required audio file not found at: {audio_path}")
    if not os.path.exists(scenes_dir) or not os.path.isdir(scenes_dir):
        raise FileNotFoundError(f"Scenes directory not found at: {scenes_dir}")
        
    valid_ext = ('.png', '.jpg', '.jpeg', '.webp')
    images = sorted([f for f in os.listdir(scenes_dir) if f.lower().endswith(valid_ext)])
    if not images:
        raise FileNotFoundError(f"No scene images found in: {scenes_dir}")
        
    if progress_callback:
        await progress_callback(10)
        
    # 2. Timing calculations
    duration = await get_audio_duration(audio_path)
    secs_per_image = duration / len(images)
    
    if progress_callback:
        await progress_callback(20)
        
    # 3. Create Concat Temp File
    # We must use safe paths and format correctly.
    # Note: tempfile.NamedTemporaryFile on Windows has file-sharing lock issues if we don't close it before FFmpeg reads it.
    concat_fd, concat_path = tempfile.mkstemp(suffix=".txt", text=True)
    try:
        with os.fdopen(concat_fd, 'w', encoding='utf-8') as concat_file:
            for img in images:
                img_path = os.path.join(scenes_dir, img).replace('\\', '/')
                concat_file.write(f"file '{img_path}'\n")
                concat_file.write(f"duration {secs_per_image}\n")
            # Concat needs the last image repeated once more to register the duration of the last slide
            last_img = os.path.join(scenes_dir, images[-1]).replace('\\', '/')
            concat_file.write(f"file '{last_img}'\n")
            
        if progress_callback:
            await progress_callback(30)
            
        # 4. Build filtergraphs
        w, h = resolution.split('x')
        vf = (
            f'scale={w}:{h}:force_original_aspect_ratio=decrease,'
            f'pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,'
            f'zoompan=z=min(zoom+{zoom_speed}\\,1.2):'
            f'd={int(secs_per_image*fps)}:x=iw/2-(iw/zoom/2):'
            f'y=ih/2-(ih/zoom/2):s={w}x{h}:fps={fps}'
        )
        
        cmd = [
            FFMPEG_PATH, '-y',
            '-f', 'concat', '-safe', '0', '-i', concat_path,
            '-i', audio_path,
            '-c:v', 'libx264', '-preset', 'medium',
            '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '192k',
            '-vf', vf,
            '-shortest',
            '-movflags', '+faststart',
            output_path
        ]
        
        if progress_callback:
            await progress_callback(40)
            
        # 5. Run async process
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Read stderr to monitor logs if needed, or simply wait
        # We can simulate progress updates based on time since FFmpeg doesn't output straightforward percentage.
        # But we can just wait for completion.
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            err_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
            raise RuntimeError(f"FFmpeg compilation failed: {err_msg[-500:]}")
            
    finally:
        # 6. Clean up temporary concat file
        try:
            if os.path.exists(concat_path):
                os.unlink(concat_path)
        except Exception:
            pass
            
    if progress_callback:
        await progress_callback(100)
        
    return output_path
