import re
from dataclasses import dataclass

from selenium.webdriver.common.by import By

from app.infra.browser import create_chrome_driver


@dataclass
class JableVideoMetadata:
    title: str
    cover_url: str
    m3u8_url: str


class JableProvider:
    def __init__(self, user_agent: str, logger):
        self.user_agent = user_agent
        self.logger = logger

    def fetch_metadata(self, url: str) -> JableVideoMetadata:
        driver = create_chrome_driver(self.user_agent)
        try:
            driver.get(url)
            title = driver.find_element(By.XPATH, "//meta[@property='og:title']").get_attribute("content")
            cover_url = driver.find_element(By.XPATH, "//meta[@property='og:image']").get_attribute("content")
            m3u8_match = re.search("https://.+m3u8", driver.page_source)
        finally:
            driver.quit()

        if not m3u8_match:
            raise ValueError("m3u8 not found")

        return JableVideoMetadata(
            title=title,
            cover_url=cover_url,
            m3u8_url=m3u8_match[0],
        )
