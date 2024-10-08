import argparse
import calendar
from pathlib import Path
import json
from typing import List, Callable, Union
from dataclasses import dataclass
from abc import ABC, abstractmethod
import re
import os
import time
import string
import importlib
import sys
import logging

from pdf2image import convert_from_path
import pytesseract

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    style='%',
    datefmt='%Y-%m-%d %H:%M',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)


def import_from_path(module_name, file_path):
    """Import a module given its name and file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class BaseFileParser(ABC):

    @abstractmethod
    def to_text(self, file_path: Path, cache: bool=True) -> str:
        pass
    @abstractmethod
    def to_transactions(self, text: str) -> bool:
        pass

    def read_cache(self, file_path: Path) -> Union[None,str]:
        pass

    def write_cache(self, file_path: Path, text: str):
        pass
        
    def delete_cache(self, file_path):
        pass

    def get_text(self, file_path: Path, use_cache: bool = True, clear_cache: bool=False) -> str:
        if clear_cache:
            self.delete_cache(file_path)
        text = None
        from_cache = False
        if use_cache and not clear_cache:
            text = self.read_cache(file_path)
            if text is not None:
                from_cache = True
        if text is None:
            text = self.to_text(file_path)
        if text and not from_cache and use_cache:
            self.write_cache(file_path, text)
        return text


class PdfParser(BaseFileParser):
    '''A generic parser for PDF statements'''
    
    def __init__(self, page_min=0, page_max=None):
        super().__init__()
        self.page_min = page_min
        self.page_max = page_max

    def pdf_to_text(pdf_path: Path, page_min: int=0, page_max: int=None) -> str:
        '''Reads the PDF at the given path and turns it into text using OCR'''
        page_images = convert_from_path(pdf_path)
        page_max = len(page_images) if page_max is None else page_max
        # print(f'Converting {pdf_path} to text')
        text = ''
        for image in list(page_images)[page_min:page_max]:
            text += pytesseract.image_to_string(image)
        return text

    def read_cache(self, file_path: Path) -> str:
        cached_text_file = file_path.parent / (file_path.stem + '.txt')
        if cached_text_file.is_file():
            return cached_text_file.read_text()
        return None
        
    def write_cache(self, file_path: Path, text):
        cached_text_file = file_path.parent / (file_path.stem + '.txt')
        logger.debug(f'Writing to cache {cached_text_file}')
        cached_text_file.write_text(text)
        
    def delete_cache(self, file_path: Path) -> str:
        cached_text_file = file_path.parent / (file_path.stem + '.txt')
        cached_text_file.unlink(missing_ok=True)
        
    def to_text(self, file_path: Path) -> str:
        return PdfParser.pdf_to_text(file_path, page_min=self.page_min, page_max=self.page_max)

class PdfTestParser(PdfParser):
    def to_transactions(self, text: str):
        raise ValueError('This parser is only for outputing text!')




def run_parsers(statement_paths: List[Path], parsers: List[BaseFileParser], output_dir: Path, use_cache: bool=True, clear_cache: bool = False, only_text:bool=False) -> List[dict]:
    # TODO make async
    # TODO use logger
    all_transactions = []
    if only_text:
        use_cache=True
        clear_cache=True
    for pdf_path in statement_paths:
        print(f'Processing {pdf_path}')
        logger.info(f'Processing {pdf_path}')
        transactions_file = pdf_path.parent / (pdf_path.stem + '_transactions.json')
        found_parser = False
        for parser in parsers:
            try:
                logger.debug(f'Attempting parser: {type(parser).__name__}')
                text = parser.get_text(pdf_path, use_cache=use_cache, clear_cache=clear_cache)
                if text:
                    if only_text:
                        break
                    transactions = list(parser.to_transactions(text))
                    logger.debug(f'Read {len(transactions)} using {type(parser).__name__}')
                    if transactions:
                        found_parser = True
                        logger.debug('Trying no more parsers')
                        all_transactions.extend(transactions)
                        break
                    else:
                        logger.debug('Trying next parser')
            except ValueError as e:
                logger.error(f'Error parsing {pdf_path}: {e}')
                logger.debug('Trying next parser')
        if not found_parser:
            raise ValueError(f'No parser returned transactions for {pdf_path}!')
    month_groups = {}
    for t in all_transactions:
        key = t['date'][:-3] # remove day of month
        ts = month_groups.get(key, [])
        ts.append(t)
        month_groups[key] = ts
    for mo, ts in month_groups.items():
        output_file = output_dir / (f'{mo}-transactions.json')
        logger.info(f'Writing transactions to {output_file}')
        ts = sorted(ts, key=lambda k: k['date'])
        output_file.write_text(json.dumps(ts, indent=2))

DEFAULT_CONFIG = {
    "parsers": [],
}
def parse_config(config_path: Path) -> dict:
    config = json.loads(config_path.read_text())
    config = {**DEFAULT_CONFIG, **config}
    return config

def create_parsers(parser_configs: List[dict]) -> List[BaseFileParser]:
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


def main():
    parser = argparse.ArgumentParser(description='A tool to export transactions from bank statements')
    parser.add_argument('statement_paths', nargs='+', type=existing_file, help='Paths to statement files')
    parser.add_argument('-c', '--config', type=existing_file, help='Paths to a config file')
    parser.add_argument('-o', '--output-dir', type=Path, default=Path.cwd(), help='Directory to output transaction files')
    parser.add_argument('--no-cache', action='store_true', help='Force re-reading and parsing statement files')
    parser.add_argument('--clear-cache', action='store_true', help='Remove existing cache for each file, but still write out to the cache (unless --no-cache is enabled)')
    parser.add_argument('--pdf-to-text', action='store_true', help='Output PDF files as text for reference to build a custom parser. Skips parsing transactions')
    parser.add_argument('--parsers', default=None, help='A subset of parsers from the config.json to use. Useful to provide a single one to test its output')
    args = parser.parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    statement_paths = args.statement_paths
    config = parse_config(args.config)
    parser_objs = config.get('parsers', [])
    if args.parsers:
        parser_objs = list(filter(lambda p: p['type'] in args.parsers, parser_objs))
    parsers = create_parsers(parser_objs)
    run_parsers(statement_paths, parsers, output_dir, use_cache=not args.no_cache, clear_cache=(args.no_cache or args.clear_cache), only_text=args.pdf_to_text)

    
if __name__ == '__main__':
    main()
