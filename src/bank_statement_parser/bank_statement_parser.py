import argparse
import calendar
from pathlib import Path
import json
from typing import List, Callable
from dataclasses import dataclass
from abc import ABC, abstractmethod
import re
import os
import time
import string
import importlib
import sys

from pdf2image import convert_from_path
import pytesseract

def import_from_path(module_name, file_path):
    """Import a module given its name and file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class BaseParser(ABC):

    @abstractmethod
    def to_text(self, file_path: Path, cache: bool=True) -> str:
        pass
    @abstractmethod
    def to_transactions(self, text: str) -> bool:
        pass
        
def pdf_to_text(pdf_path: Path, page_min: int=0, page_max: int=None) -> str:
    '''Reads the PDF at the given path and turns it into text using OCR'''
    page_images = convert_from_path(pdf_path)
    page_max = len(page_images) if page_max is None else page_max
    print(f'Converting {pdf_path} to text')
    text = ''
    for image in list(page_images)[page_min:page_max]:
        text += pytesseract.image_to_string(image)
    return text

class PdfParser(BaseParser):
    '''A generic parser for PDF statements'''
    
    def __init__(self, page_min=0, page_max=None):
        super().__init__()
        self.page_min = page_min
        self.page_max = page_max
        
    def to_text(self, file_path: Path, use_cache=True):
        cached_text_file = file_path.parent / (file_path.stem + '.txt')
        text = None
        used_cache = False
        # TODO move cache logic to own fn
        if use_cache and cached_text_file.is_file():
            cache_time = int(os.path.getmtime(cached_text_file))
            file_time = int(os.path.getmtime(file_path))
            if cache_time >= file_time:
                used_cache = True
                print(f'Reading from cache file: {cached_text_file}')
                text = cached_text_file.read_text()
                
        if not used_cache:
            text = pdf_to_text(file_path, page_min=self.page_min, page_max=self.page_max)

        if use_cache and not used_cache:
            print(f'Writing cache file: {cached_text_file}')
            cached_text_file.write_text(text)
        return text

def PdfTestParser(PdfParser):
    def to_transactions(self, text: str):
        raise ValueError('This parser is only for outputing text!')

def run_parsers(statement_paths: List[Path], parsers: List[BaseParser], output_dir: Path, use_cache=True) -> List[dict]:
    # TODO make async
    # TODO use logger
    all_transactions = []
    for pdf_path in statement_paths:
        print(f'Processing {pdf_path}')
        transactions_file = pdf_path.parent / (pdf_path.stem + '_transactions.json')
        for parser in parsers:
            text = parser.to_text(pdf_path, use_cache=use_cache)
            if text:
                try:
                    transactions = parser.to_transactions(text)
                    if transactions:
                        all_transactions.extend(transactions)
                        break
                except ValueError as e:
                    print(f'Error parsing {pdf_path}: {e}')

    month_groups = {}
    for t in all_transactions:
        key = t['date'][:-3] # remove day of month
        ts = month_groups.get(key, [])
        ts.append(t)
        month_groups[key] = ts
    for mo, ts in month_groups.items():
        output_file = output_dir / (f'{mo}-transactions.json')
        print(f'Writing transactions to {output_file}')
        ts = sorted(ts, key=lambda k: k['date'])
        output_file.write_text(json.dumps(ts, indent=2))

DEFAULT_CONFIG = {
    "parsers": [],
}
def parse_config(config_path: Path) -> dict:
    config = json.loads(config_path.read_text())
    config = {**DEFAULT_CONFIG, **config}
    return config

def create_parsers(parser_configs: List[dict]) -> List[BaseParser]:
    parsers = []
    for parser_config in parser_configs:
        parser_class = parser_config['type']
        args = parser_config.get('args', [])
        kwargs = parser_config.get('kwargs', {})
        module_object = None
        # import module from py file or from python path
        if (module_path := parser_config.get('module_path', None)):
            module_name = parser_config.get('module_name', Path(module_path).stem)
            module_object = import_from_path(module_name, module_path)
        else:
            module_name = parser_config.get('module_name', 'bank_statement_parser')
            module_object = importlib.import_module(module_name)
        
        ParserClass = getattr(module_object, parser_class)
        p = ParserClass(*args, **kwargs)
        parsers.append(p)
    return parsers
            
def existing_file(p: str) -> Path:
    p = Path(p)
    if p.is_file():
        return p
    raise argparse.ArgumentError(f"Path {p} must be an existing file")

def output_pdfs_to_text(statement_paths: List[Path]):
    parser = PdfTestParser()
    for p in statement_paths:
        parser.to_text(p, use_cache=True)
    
def _main():
    parser = argparse.ArgumentParser(description='A tool to export transactions from bank statements')
    parser.add_argument('statement_paths', nargs='+', type=existing_file, help='Paths to statement files')
    parser.add_argument('-c', '--config', type=existing_file, help='Paths to a config file')
    parser.add_argument('-o', '--output-dir', type=Path, default=Path.cwd(), help='Directory to output transaction files')
    parser.add_argument('--pdf-to-text', action='store_true', help='Output PDF files as text for reference to build a custom parser. Skips parsing transactions')
    args = parser.parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    statement_paths = args.statement_paths
    if args.pdf_to_text:
        output_to_text(statement_paths)
    else:
        config = parse_config(args.config)
        parsers = create_parsers(config.get('parsers', []))
        run_parsers(statement_paths, parsers, output_dir)

    
if __name__ == '__main__':
    main()
