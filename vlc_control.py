# vlc_control.py
import socket
import logging

def send_command_to_vlc(command, host='127.0.0.1', port=4212):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((host, port))
            sock.sendall(f"{command}\n".encode('utf-8'))
            response = sock.recv(4096).decode('utf-8')
            return response.strip()
    except Exception as e:
        logging.error(f"Error sending command to VLC: {e}")
        return None
