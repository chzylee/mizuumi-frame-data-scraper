# mizuumi-frame-data-scraper

Python web scraper using `requests` and `BeautifulSoup4` to scrape frame data from Mizuumi wiki pages.

This project is created with the intent of uploading scraped data to AWS DynamoDB for use with Discord bots.

## Testing

The meat of this app will not be tested as it would be self explanatory from data obtained from scraping. Unit tests will, however, be written for utility modules that contain basic logic. Tests should be run from `src` directory.

Run unit tests with `python -m unittest discover -s tests -p "*_tests.py"` from the project.

Test run the scraper on saved wiki page HTML by running script directly: `python "./tests/scraper_integrationtest.py"`

## Updating DynamoDB

[uploader.py](./src/uploader.py) loops thru ALL characters and finds data which is stored locally and not committed.

[edit_data.py](./src/edit_data.py) has Character and Moon set **in the code** and updates the data to match what is in the corresponding file.
