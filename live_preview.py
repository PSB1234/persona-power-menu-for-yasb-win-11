import sys
import os
import time
import subprocess

def stop_process(process):
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_to_watch = os.path.join(base_dir, "p3r_power.py")
    
    if not os.path.exists(file_to_watch):
        print(f"Error: Could not find {file_to_watch}")
        return

    last_mtime = os.path.getmtime(file_to_watch)
    print("==================================================")
    print(" LIVE PREVIEW MODE ACTIVE")
    print("==================================================")
    print("1. Open p3r_power.py in your code editor.")
    print("2. Put your editor on the LEFT side of the screen.")
    print("3. Edit the X, Y, size, or rotation values.")
    print("4. Hit SAVE (Ctrl+S). The menu will instantly update!")
    print("--------------------------------------------------")
    print("Press Ctrl+C in this terminal to stop.")
    
    # Start the preview process
    process = subprocess.Popen([sys.executable, file_to_watch, "--preview"])

    try:
        while True:
            time.sleep(0.5)
            current_mtime = os.path.getmtime(file_to_watch)
            if current_mtime != last_mtime:
                print("\n[+] Changes saved! Reloading preview...")
                stop_process(process)
                
                # Restart the process
                process = subprocess.Popen([sys.executable, file_to_watch, "--preview"])
                last_mtime = current_mtime
    except KeyboardInterrupt:
        print("\nStopping live preview...")
        stop_process(process)

if __name__ == '__main__':
    main()
