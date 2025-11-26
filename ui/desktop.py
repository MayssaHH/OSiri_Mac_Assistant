"""
OSiri Desktop App - Codex-like floating window
Opens the OSiri web UI in a native Mac window
"""

import subprocess
import sys
import time
import threading
import signal
import webview

# Configuration
WEB_UI_URL = "http://127.0.0.1:7860"
WINDOW_WIDTH = 420
WINDOW_HEIGHT = 640


class OSiriDesktopApp:
    def __init__(self):
        self.server_process = None
        self.window = None
        
    def start_server(self):
        """Start the Gradio server in the background."""
        print("🚀 Starting OSiri web server...")
        self.server_process = subprocess.Popen(
            [sys.executable, "app.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=sys.path[0] or "."
        )
        
        # Wait for server to be ready
        time.sleep(3)
        print("✅ Server started!")
        
    def stop_server(self):
        """Stop the Gradio server."""
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
        
        # Wait a bit for server to start
        time.sleep(4)
        
        # Create the floating window
        self.window = webview.create_window(
            title="OSiri",
            url=WEB_UI_URL,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            resizable=True,
            on_top=True,  # Always on top (Codex-like!)
            confirm_close=False,
            background_color='#f5f5f7'  # Mac-like background
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
    ║         🍎 OSiri Desktop App          ║
    ║   Your AI-powered Mac Assistant       ║
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

