"""
OSiri Desktop App - Siri-like floating command bar
A minimal floating window that stays at the bottom center of the screen
"""

import subprocess
import sys
import time
import threading
import signal
import webview

# Configuration
WEB_UI_URL = "http://127.0.0.1:7861"  # Siri UI port
WINDOW_WIDTH = 650
WINDOW_HEIGHT = 400


class OSiriDesktopApp:
    def __init__(self):
        self.server_process = None
        self.window = None
        
    def start_server(self):
        """Start the Siri UI server in the background."""
        print("🚀 Starting OSiri server...")
        self.server_process = subprocess.Popen(
            [sys.executable, "siri_ui.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=sys.path[0] or "."
        )
        
        # Wait for server to be ready
        time.sleep(2)
        print("✅ Server started!")
        
    def stop_server(self):
        """Stop the server."""
        if self.server_process:
            print("🛑 Stopping server...")
            self.server_process.terminate()
            self.server_process.wait()
            
    def on_closed(self):
        """Handle window close."""
        self.stop_server()
        
    def run(self):
        """Run the desktop app."""
        # Start the web server in a thread
        server_thread = threading.Thread(target=self.start_server, daemon=True)
        server_thread.start()
        
        # Wait for server to start
        time.sleep(3)
        
        # Create the floating window - frameless and transparent
        self.window = webview.create_window(
            title="OSiri",
            url=WEB_UI_URL,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            resizable=False,
            frameless=True,  # No window chrome
            easy_drag=True,  # Allow dragging anywhere
            on_top=True,  # Always on top
            transparent=True,  # Transparent background!
        )
        
        # Handle graceful shutdown
        def on_close():
            self.stop_server()
            
        self.window.events.closed += on_close
        
        # Start the webview
        webview.start(
            debug=False,
            gui='cocoa'  # Native macOS rendering
        )


def main():
    """Main entry point."""
    print("""
    ╔═══════════════════════════════════════╗
    ║         🍎 OSiri Command Bar          ║
    ║     Siri-style floating assistant     ║
    ╚═══════════════════════════════════════╝
    """)
    
    app = OSiriDesktopApp()
    
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\n👋 Shutting down OSiri...")
        app.stop_server()
        sys.exit(0)
        
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        app.run()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        app.stop_server()


if __name__ == "__main__":
    main()
