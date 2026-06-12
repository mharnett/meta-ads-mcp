"""Callback server for Meta Ads API authentication."""

import threading
import socket
import asyncio
import json
import logging
import secrets
import time
import webbrowser
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
from typing import Dict, Any, Optional

from .utils import logger

# Global token container for communication between threads.
# `expected_state` is the CSRF state minted when the auth URL is generated;
# the callback only accepts a code if the returned state matches it.
token_container = {"token": None, "expires_in": None, "user_id": None}


def validate_and_store_callback(code: Optional[str], state: Optional[str]) -> bool:
    """Validate the OAuth callback's CSRF state and store the auth code if valid.

    Authorization-code flow CSRF protection: the `state` returned by the
    provider must match the high-entropy value we minted in
    ``AuthManager.get_auth_url`` (stored as ``token_container['expected_state']``).
    A mismatch — or an inbound callback when no flow was initiated — indicates a
    forged / CSRF callback, so the code is rejected and NOT stored.

    Returns:
        True if the state validated and the code was stored, False otherwise.
    """
    expected = token_container.get("expected_state")

    if not expected:
        logger.error("OAuth callback rejected: no expected state (no flow initiated)")
        return False
    if not state:
        logger.error("OAuth callback rejected: missing state parameter (possible CSRF)")
        return False

    # Constant-time comparison to avoid leaking the state via timing.
    if not secrets.compare_digest(str(state), str(expected)):
        logger.error("OAuth callback rejected: state mismatch (possible CSRF)")
        return False

    if not code:
        logger.error("OAuth callback rejected: state valid but no code present")
        return False

    token_container["auth_code"] = code
    token_container["state"] = state
    token_container["timestamp"] = time.monotonic()
    # Single-use: consume the expected state so a replayed callback can't reuse it.
    token_container["expected_state"] = None
    logger.info("OAuth callback accepted: state validated, authorization code stored")
    return True

# Global variables for server thread and state
callback_server_thread = None
callback_server_lock = threading.Lock()
callback_server_running = False
callback_server_port = None
callback_server_instance = None
server_shutdown_timer = None

# Timeout in seconds before shutting down the callback server
CALLBACK_SERVER_TIMEOUT = 180  # 3 minutes timeout


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            logger.debug(f"Callback server received request: {self.path}")

            if self.path.startswith("/callback"):
                self._handle_oauth_callback()
            else:
                # If no matching path, return a 404 error
                self.send_response(404)
                self.end_headers()
        except Exception as e:
            logger.error(f"Error processing request: {e}")
            self.send_response(500)
            self.end_headers()
    
    def _handle_oauth_callback(self):
        """Handle OAuth callback after user authorization"""
        # Check if we're being redirected from Facebook with an authorization code
        parsed_url = urlparse(self.path)
        params = parse_qs(parsed_url.query)
        
        # Check for code parameter
        code = params.get('code', [None])[0]
        state = params.get('state', [None])[0]
        error = params.get('error', [None])[0]
        
        # Send 200 OK response with a simple HTML page
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        
        if error:
            # User denied access or other error occurred
            html = f"""
            <html>
            <head><title>Authorization Failed</title></head>
            <body>
                <h1>Authorization Failed</h1>
                <p>Error: {error}</p>
                <p>The authorization was cancelled or failed. You can close this window.</p>
            </body>
            </html>
            """
            logger.error(f"OAuth authorization failed: {error}")
        elif code and validate_and_store_callback(code, state):
            # Success case - authorization code received AND CSRF state validated.
            # The auth module will exchange this code for an access token.
            html = """
            <html>
            <head><title>Authorization Successful</title></head>
            <body>
                <h1>✅ Authorization Successful!</h1>
                <p>You have successfully authorized the Meta Ads MCP application.</p>
                <p>You can now close this window and return to your application.</p>
                <script>
                    // Try to close the window automatically after 2 seconds
                    setTimeout(function() {
                        window.close();
                    }, 2000);
                </script>
            </body>
            </html>
            """
            logger.info("OAuth authorization successful")
        elif code:
            # Code present but state validation failed -> reject (possible CSRF).
            html = """
            <html>
            <head><title>Authorization Rejected</title></head>
            <body>
                <h1>Authorization Rejected</h1>
                <p>The authorization could not be verified (state validation failed).</p>
                <p>This may indicate a CSRF attempt. Please restart authentication.</p>
            </body>
            </html>
            """
            logger.error("OAuth callback rejected: state validation failed")
        else:
            # No code or error - something unexpected happened
            html = """
            <html>
            <head><title>Unexpected Response</title></head>
            <body>
                <h1>Unexpected Response</h1>
                <p>No authorization code or error received. Please try again.</p>
            </body>
            </html>
            """
            logger.warning("OAuth callback received without code or error")
        
        self.wfile.write(html.encode())

    # Silence server logs
    def log_message(self, format, *args):
        return


def shutdown_callback_server():
    """
    Shutdown the callback server if it's running
    """
    global callback_server_thread, callback_server_running, callback_server_port, callback_server_instance, server_shutdown_timer

    with callback_server_lock:
        if not callback_server_running:
            logger.debug("Callback server is not running")
            return

        if server_shutdown_timer is not None:
            server_shutdown_timer.cancel()
            server_shutdown_timer = None

        try:
            if callback_server_instance:
                logger.info("Shutting down callback server...")
                callback_server_instance.shutdown()
                callback_server_instance.server_close()
                logger.info("Callback server shut down successfully")

            if callback_server_thread and callback_server_thread.is_alive():
                callback_server_thread.join(timeout=5)
                if callback_server_thread.is_alive():
                    logger.warning("Callback server thread did not shut down cleanly")
        except Exception as e:
            logger.error(f"Error during callback server shutdown: {e}")
        finally:
            callback_server_running = False
            callback_server_thread = None
            callback_server_port = None
            callback_server_instance = None


def start_callback_server() -> int:
    """
    Start the callback server and return the port number it's running on.
    
    Returns:
        int: Port number the server is listening on
        
    Raises:
        Exception: If the server fails to start
    """
    global callback_server_thread, callback_server_running, callback_server_port, callback_server_instance, server_shutdown_timer
    
    # Check if callback server is disabled
    if os.environ.get("META_ADS_DISABLE_CALLBACK_SERVER"):
        raise Exception("Callback server is disabled via META_ADS_DISABLE_CALLBACK_SERVER environment variable")
    
    with callback_server_lock:
        if callback_server_running:
            logger.info(f"Callback server already running on port {callback_server_port}")
            return callback_server_port
        
        # Find an available port
        port = 8080
        max_attempts = 10
        for attempt in range(max_attempts):
            try:
                # Test if port is available
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('localhost', port))
                break
            except OSError:
                port += 1
        else:
            raise Exception(f"Could not find an available port after {max_attempts} attempts")
        
        callback_server_port = port
        
        # Start the server in a separate thread
        callback_server_thread = threading.Thread(target=server_thread, daemon=True)
        callback_server_thread.start()
        
        # Wait a moment for the server to start
        import time
        time.sleep(0.5)
        
        if not callback_server_running:
            raise Exception("Failed to start callback server")
        
        # Set up automatic shutdown timer
        def auto_shutdown():
            logger.info(f"Callback server auto-shutdown after {CALLBACK_SERVER_TIMEOUT} seconds")
            shutdown_callback_server()

        server_shutdown_timer = threading.Timer(CALLBACK_SERVER_TIMEOUT, auto_shutdown)
        server_shutdown_timer.start()

        logger.info(f"Callback server started on http://localhost:{port}")
        return port


def server_thread():
    """Thread function to run the callback server"""
    global callback_server_running, callback_server_instance

    try:
        callback_server_instance = HTTPServer(('localhost', callback_server_port), CallbackHandler)
        callback_server_running = True
        logger.debug(f"Callback server thread started on port {callback_server_port}")
        callback_server_instance.serve_forever()
    except Exception as e:
        logger.error(f"Callback server error: {e}")
        callback_server_running = False
    finally:
        logger.debug("Callback server thread finished")
        callback_server_running = False 