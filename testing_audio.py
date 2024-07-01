import pyaudio
import wave

# Record audio
def record_audio(filename, duration=5):
    audio = pyaudio.PyAudio()
    stream = audio.open(format=pyaudio.paInt16, channels=1, rate=44100, input=True, frames_per_buffer=1024)
    frames = []

    print(f"Recording audio for {duration} seconds...")

    for _ in range(int(44100 / 1024 * duration)):
        data = stream.read(1024)
        frames.append(data)
        print(f"Recorded frame size: {len(data)}")

    stream.stop_stream()
    stream.close()
    audio.terminate()

    print(f"Saving recorded audio to {filename}...")

    wf = wave.open(filename, 'wb')
    wf.setnchannels(1)
    wf.setsampwidth(audio.get_sample_size(pyaudio.paInt16))
    wf.setframerate(44100)
    wf.writeframes(b''.join(frames))
    wf.close()

    print("Recording saved.")

# Play audio
def play_audio(filename):
    print(f"Playing audio from {filename}...")

    wf = wave.open(filename, 'rb')
    audio = pyaudio.PyAudio()
    stream = audio.open(format=audio.get_format_from_width(wf.getsampwidth()),
                        channels=wf.getnchannels(),
                        rate=wf.getframerate(),
                        output=True)

    data = wf.readframes(1024)
    while data:
        stream.write(data)
        data = wf.readframes(1024)
        print(f"Played frame size: {len(data)}")

    stream.stop_stream()
    stream.close()
    audio.terminate()

    print("Playback finished.")

# Test recording and playback
record_audio('test_audio.wav', duration=5)
play_audio('test_audio.wav')
