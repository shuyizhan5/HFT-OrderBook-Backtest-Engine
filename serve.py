#!/usr/bin/env python3
import http.server
import socketserver
import os

os.chdir('/Users/zhanshuyi/Downloads/QTProject1')

PORT = 8000

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        return super().end_headers()

with socketserver.TCPServer(("", PORT), MyHTTPRequestHandler) as httpd:
    print(f"✅ Server started at http://localhost:{PORT}")
    print(f"📄 Open http://localhost:{PORT}/backtest_report.html in your browser")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n✅ Server stopped")
