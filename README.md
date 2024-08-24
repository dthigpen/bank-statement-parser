# bank-statement-parser
A command line tool to parse bank statements into JSON formatted transactions. Used as input for the budgeting tool [budget-cli](https://github.com/dthigpen/budget-cli).

```
$ bank-statement-parser -c config.json path/to/statements/*.pdf
$ ls *.json
2024-04-transactions.json
2024-05-transactions.json
2024-06-transactions.json
2024-07-transactions.json
...
$ cat 2024-04-transactions.json
[
	{
	    "date": "2024-04-06",        
	    "description": "WM SUPERCENTER #1234",
	    "amount": 39.45,
	    "account": "Chase Credit Card"        
	}
	...
]
```

## Installation
1. Make a new directory and Python environment
    ```
    $ mkdir my_finances
    $ cd my_finances
    $ python -m venv venv
    $ source ./venv/bin/activate
    ```
2. Install `bank-statement-parser`
    ```
    $ pip install git+https://github.com/dthigpen/bank-statement-parser
    ```
3. Run `bank-statement-parser` commands. See Usage for details.
    ```
    $ bank-statement-parser --help
    ```

## Usage

1. Create a `config.json` file with the following (Feel free to replace `MyBank` with something more meaningful). This will be used to tell bank-statement-parser how to parse your statements.
    ```json
    {
        "parsers": [
            "type": "MyBankParser",
            "module_path": "bank_parsers.py"
        ]
    }
    ```
2. Next create `bank_parsers.py`. This will contain the specific logic parsing your own bank's statement into transactions.
    ```python
    from bank_statement_parser import PdfParser

    class MyBankParser(PdfParser):
        def to_transactions(self, text: str):
            pass
    ```
3. Next generate a sample of text extracted from your bank's PDF statement by running the following. A `.txt` file will be generated in the statement directory.
    ```
    $ bank-statement-parser path/to/statement.pdf --pdf-to-text
    ```
4. Open `statement.txt` in a text editor and find the transactions. For example:
    ```txt
    07/11/2024 07/12/2024 SUPER MARKET #12 99.23
    07/15/2024 07/152024 GAS STATION 45.89
    ...
    ```
5. Fill in the `to_transactions` function stubbed out earlier with logic to extract these fields and `yield` a transaction for each one.
    ```python
    import re
    from bank_statement_parser import PdfParser

    class MyBankParser(PdfParser):
        def to_transactions(self, text: str):
            # TODO do something with regular expressions
            for match in matches:
                # some more logic
                yield {
                    'date': date, # e.g. "2024-07-11" format
                    'amount': amount, # e.g. 123.12
                    'description': desc, # e.g. "SUPER MARKET #12"
                    'account': 'My Bank Credit Card',
                }
    ```
6. Run the parser on the statements. JSON transaction files will populate the current directory.
    ```
    $ bank-statement-parser -c config.json path/to/statements/*.pdf
    ```

## TODO

- Add a generic regex parser so that custom Python parsers are not needed for each bank.
- Validate parser output contains all required transaction fields
- Better caching paradigm
- Parallel processing
- Make config module path vs module name more simple
- Upload to PyPi

