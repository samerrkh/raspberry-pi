import pyaudio

def list_audio_devices():
    audio = pyaudio.PyAudio()
    print("Available audio devices:")
    for i in range(audio.get_device_count()):
        info = audio.get_device_info_by_index(i)
        print(f"Device {i}: {info['name']} - {'Input' if info['maxInputChannels'] > 0 else 'Output'}")
    audio.terminate()

list_audio_devices()
