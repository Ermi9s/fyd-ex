import http.server
import socketserver
import tempfile
import json
import os
from main import parse_id_card

class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/parse':
            try:
                content_length = int(self.headers['Content-Length'])
                pdf_data = self.rfile.read(content_length)
                
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                    tmp.write(pdf_data)
                    pdf_path = tmp.name
                
                try:
                    result = parse_id_card(pdf_path)
                    response = json.dumps(result, ensure_ascii=False)
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(response.encode('utf-8'))
                finally:
                    os.unlink(pdf_path)
                    for f in os.listdir('.'):
                        if f.startswith('extracted_'):
                            try:
                                os.unlink(f)
                            except:
                                pass
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_GET(self):
        self.send_response(404)
        self.end_headers()

if __name__ == '__main__':
    PORT = int(os.environ.get('PORT', 8000))
    print(f"Server Starting...")
    print(f"Port: {PORT}")
    print(f"Endpoint: POST /parse")
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Server successfully started on port {PORT}")
        print(f"Ready to accept requests...")
        httpd.serve_forever()