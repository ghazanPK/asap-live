"""Local screenplay-to-3D demo. Run from an independently cloned ASAP repository."""
from pathlib import Path
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
import argparse,json,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'scripts'))
from asap_multi.core import compile_timeline,parse_screenplay
from speech_backend import SpeechBackend,speech_route
from beat_runtime import serve_beat
SPEECH=SpeechBackend()

def compile_request(payload):
    if not isinstance(payload,dict):raise ValueError('Request must be a JSON object.')
    if payload.get('format','txt') not in ('txt','fdx'):raise ValueError('Format must be txt or fdx.')
    script=payload.get('script','')
    if not isinstance(script,str) or not script.strip() or len(script)>200000:raise ValueError('Supply a nonempty screenplay up to 200,000 characters.')
    library=payload.get('library')
    if not isinstance(library,dict) or not isinstance(library.get('characters'),dict) or not library['characters']:raise ValueError('The catalog must declare a nonempty characters mapping.')
    suffix='.fdx' if payload.get('format')=='fdx' else '.txt'
    with tempfile.TemporaryDirectory() as directory:
        file=Path(directory)/('input'+suffix);file.write_text(script,encoding='utf-8')
        paragraphs=parse_screenplay(file)
    if not paragraphs:raise ValueError('No supported screenplay paragraphs found.')
    return compile_timeline(paragraphs,library)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT/'static'),**kwargs)
    def json(self,result,status=200):
        body=json.dumps(result,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if serve_beat(self,ROOT,'automatic'):return
        if self.path=='/api/example':self.json({'script':(ROOT/'examples/screenplay.txt').read_text(encoding='utf-8'),'library':json.loads((ROOT/'examples/library.json').read_text(encoding='utf-8'))});return
        if self.path=='/api/speech':self.json(SPEECH.status());return
        super().do_GET()
    def do_POST(self):
        if serve_beat(self,ROOT,'automatic'):return
        if speech_route(self,SPEECH):return
        if self.path!='/api/compile':self.json({'error':'Unknown API route'},404);return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=1024*1024:raise ValueError('Request must be at most 1 MB.')
            self.json(compile_request(json.loads(self.rfile.read(length))))
        except Exception as exc:self.json({'error':str(exc)},400)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=8010);parser.add_argument('--host',default='127.0.0.1');args=parser.parse_args()
    print(f'ASAP demo: http://{args.host}:{args.port}',flush=True)
    ThreadingHTTPServer((args.host,args.port),Handler).serve_forever()

if __name__=='__main__':main()
