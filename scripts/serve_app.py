"""Serve the built frontend and local API; no npm development server needed."""
import argparse
import os
from pathlib import Path
import uvicorn
from taintlab.web.app import create_app

ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--host',default='127.0.0.1',choices=['127.0.0.1']);parser.add_argument('--port',default=8501,type=int)
    args=parser.parse_args()
    if not 1<=args.port<=65535:parser.error('Port out of range')
    os.chdir(ROOT)
    uvicorn.run(create_app(ROOT,args.port),host=args.host,port=args.port,workers=1,access_log=False,server_header=False,timeout_keep_alive=15)
if __name__=='__main__':main()
