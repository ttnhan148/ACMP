import os
import edge_tts
from typing import Dict
from pathlib import Path

# Voice mappings as defined in the Playbook
VOICES: Dict[str, str] = {
    'guy':       'en-US-GuyNeural',           # Male, professional
    'andrew':    'en-US-AndrewMultilingualNeural',  # Male, deep
    'ryan':      'en-GB-RyanNeural',           # Male, British documentary
    'jenny':     'en-US-JennyNeural',          # Female, warm
    'aria':      'en-US-AriaNeural',           # Female, engaging
    'vi_male':   'vi-VN-NamMinhNeural',        # Vietnamese male
    'vi_female': 'vi-VN-HoaiMyNeural',         # Vietnamese female
}

async def generate_voice_file(text: str, voice_preset: str, output_path: str, rate: str = "+0%") -> str:
    """
    Generates a voice audio file from text using edge-tts.
    
    Args:
        text: The text script to narrate.
        voice_preset: The key in the VOICES dictionary.
        output_path: Absolute path to save the generated audio.
        rate: Speed modifier (e.g. "+0%", "-10%").
        
    Returns:
        The output path string.
    """
    # 1. Resolve voice name
    voice_name = VOICES.get(voice_preset, VOICES['guy'])
    
    # 2. Setup output folder
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    # 3. Create edge-tts Communicate instance
    communicate = edge_tts.Communicate(text=text, voice=voice_name, rate=rate)
    
    # 4. Save to target path
    await communicate.save(output_path)
    
    return str(output_path)
