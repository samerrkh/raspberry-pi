import logging
import asyncio
import pyaudio
import websockets

# Initialize logging
logging.basicConfig(level=logging.DEBUG)

# Audio streaming setup
AUDIO_FORMAT = pyaudio.paInt16
AUDIO_CHANNELS = 1
AUDIO_RATE = 44100
AUDIO_FRAMES_PER_BUFFER = 1024

def open_audio_stream(input=True):
    audio = pyaudio.PyAudio()
    try:
        stream = audio.open(format=AUDIO_FORMAT,
                            channels=AUDIO_CHANNELS,
                            rate=AUDIO_RATE,
                            input=input,
                            output=not input,
                            frames_per_buffer=AUDIO_FRAMES_PER_BUFFER,
                            input_device_index=None if input else None,  # Use default input device
                            output_device_index=None if not input else None)  # Use default output device
        return stream, audio
    except Exception as e:
        logging.error(f"Error opening audio stream: {e}")
        if audio:
            audio.terminate()
        return None, None

async def audio_input_handler(websocket, path):
    logging.info("Audio input stream connected")
    stream, audio = open_audio_stream(input=True)
    if not stream:
        return

    try:
        while True:
            data = stream.read(AUDIO_FRAMES_PER_BUFFER, exception_on_overflow=False)
            await websocket.send(data)
            logging.debug(f"Sent audio data: {len(data)} bytes")
    except Exception as e:
        logging.error(f"Error in audio input stream: {e}")
    finally:
        logging.debug("Cleaning up audio input stream")
        stream.stop_stream()
        stream.close()
        audio.terminate()
        logging.debug("Audio input stream closed")

async def audio_output_handler(websocket, path):
    logging.info("Audio output stream connected")
    stream, audio = open_audio_stream(input=False)
    if not stream:
        return

    try:
        while True:
            data = await websocket.recv()
            stream.write(data)
            logging.debug(f"Received audio data: {len(data)} bytes")
    except Exception as e:
        logging.error(f"Error in audio output stream: {e}")
    finally:
        logging.debug("Cleaning up audio output stream")
        stream.stop_stream()
        stream.close()
        audio.terminate()
        logging.debug("Audio output stream closed")

async def start_audio_servers():
    input_server = websockets.serve(audio_input_handler, '0.0.0.0', 5001)
    output_server = websockets.serve(audio_output_handler, '0.0.0.0', 5002)

    await asyncio.gather(input_server, output_server)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_audio_servers())
    loop.run_forever()
